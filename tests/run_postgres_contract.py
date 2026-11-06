"""Run semantic contracts against a disposable PostgreSQL database per test.
Only accepts a loopback URL. Never targets a Supabase/cloud database.
"""
import os,sys,tempfile,unittest,secrets
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlsplit,urlunsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg import sql
from contextlib import contextmanager
from app.postgres import PostgresDatabase
from app.service import Service
import test_rules

base=os.environ.get('PRISMA_PG_TEST_URL','postgresql://postgres@127.0.0.1:55432/postgres')
parsed=urlsplit(base)
if parsed.hostname not in ('localhost','127.0.0.1','::1'): raise RuntimeError('Integration tests require disposable loopback Postgres, never a hosted database.')

class FixtureDatabase(PostgresDatabase):
    def connect(self):
        c=super().connect();c.set_system_context();return c

def setup(self):
    self.tmp=tempfile.TemporaryDirectory();self.database_name='prisma_test_'+secrets.token_hex(6)
    with psycopg.connect(base,autocommit=True) as c:c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(self.database_name)))
    self.db=FixtureDatabase(urlunsplit(parsed._replace(path='/'+self.database_name)));self.db.migrate();self.db.seed()
    self.time=datetime(2026,11,6,12,tzinfo=timezone.utc);self.s=Service(self.db,lambda:self.time)
    with self.db.connect() as c:self.users={r['login']:dict(r) for r in c.execute('SELECT * FROM users WHERE org=1 AND unit=1')}
    self.rec=self.users['recepcao'];self.admin=self.users['admin'];self.teacher=self.users['professor']

def teardown(self):
    with psycopg.connect(base,autocommit=True) as c:c.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(self.database_name)))
    self.tmp.cleanup()

test_rules.Fixture.setUp=setup;test_rules.Fixture.tearDown=teardown
# These two specifically assert SQLite's .backup()/file restore; Postgres has separate backup tooling.
for cls,name in [(test_rules.IncidentConfigTests,'test_backup_restore_consistent'),(test_rules.CompletionTests,'test_restore_clears_sessions_and_preserves_password')]:
    setattr(cls,name,unittest.skip('SQLite file-backup contract; provider-specific Postgres backup documented separately.')(getattr(cls,name)))

class PostgreSQLIsolationTests(test_rules.Fixture):
    def test_runtime_role_and_missing_context_fail_closed(self):
        db=PostgresDatabase(self.db.url)
        with db.connect() as c:
            self.assertEqual(c.execute('SELECT current_user').fetchone()[0],'prisma_agenda_runtime')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM people').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM reservations').fetchone()[0],0)
            c.set_context(1,2,'reception',7)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM people').fetchone()[0],0)
            self.assertEqual([r['id'] for r in c.execute('SELECT * FROM units')],[2])
            c.set_context(2,3,'admin',8)
            self.assertEqual([r['id'] for r in c.execute('SELECT * FROM units')],[3])
    def test_raw_database_rejects_cross_unit_relationship(self):
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.transaction() as c:
                c.execute("INSERT INTO reservations(org,unit,room,person,category,start,\"end\",status,payment,snapshot,created,operator) VALUES(1,1,2,5,'external','2026-11-07T08:00:00-03:00','2026-11-07T09:00:00-03:00','confirmed','confirmed','{}','2026-11-06T09:00:00-03:00',3)")
    def test_database_rejects_tutor_conflict_across_columns(self):
        import sqlite3
        with self.db.transaction() as c:
            c.execute("INSERT INTO rooms VALUES(4,1,1,'Sala 2')")
            c.execute("INSERT INTO reservations(org,unit,room,person,tutor,category,start,\"end\",status,payment,snapshot,created,operator) VALUES(1,1,1,4,1,'internal','2026-11-07T08:00:00-03:00','2026-11-07T09:00:00-03:00','confirmed','not_applicable','{}','2026-11-06T09:00:00-03:00',3)")
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.transaction() as c:
                c.execute("INSERT INTO reservations(org,unit,room,person,category,start,\"end\",status,payment,snapshot,created,operator) VALUES(1,1,4,1,'internal','2026-11-07T08:30:00-03:00','2026-11-07T09:30:00-03:00','confirmed','not_applicable','{}','2026-11-06T09:00:00-03:00',3)")

if __name__=='__main__':
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(test_rules),unittest.defaultTestLoader.loadTestsFromTestCase(PostgreSQLIsolationTests)])
    result=unittest.TextTestRunner(verbosity=2).run(suite);sys.exit(not result.wasSuccessful())
