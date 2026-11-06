"""Postgres/Supabase adapter for the existing semantic API.

Private schema only. Never put DATABASE_URL in frontend configuration.
No remote connection is created implicitly: the operator supplies a server URL.
"""
import re, sqlite3
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
from .db import Database,ROOT
from .domain import RuleError

SCHEMA='prisma_agenda'
RUNTIME_ROLE='prisma_agenda_runtime'
ID_TABLES={'organizations','units','config_versions','rooms','people','users','reservations','payments','refunds','penalties','blocks','work','schedules','swaps','reasons','audit','notifications'}

class Record(dict):
    def __getitem__(self,key):
        if isinstance(key,int): return tuple(self.values())[key]
        return super().__getitem__(key)

def record_factory(cursor):
    names=[col.name for col in (cursor.description or [])]
    def make(values):
        return Record(zip(names,[v.astimezone(timezone.utc).isoformat(timespec='seconds') if isinstance(v,datetime) else v for v in values]))
    return make

def postgres_sql(sql):
    """Translate only the small legacy SQL surface; preserve quoted literals."""
    parts=re.split(r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\")",sql)
    for i in range(0,len(parts),2):
        parts[i]=parts[i].replace('?','%s')
        parts[i]=re.sub(r'\buser\b','"user"',parts[i],flags=re.I)
        parts[i]=re.sub(r'\bend\b','"end"',parts[i],flags=re.I)
        parts[i]=re.sub(r'\bsubstr\(start,',"substr(start::text,",parts[i],flags=re.I)
    sql=''.join(parts).strip().rstrip(';')
    ignore=bool(re.match(r'INSERT\s+OR\s+IGNORE',sql,re.I))
    if ignore:
        sql=re.sub(r'^INSERT\s+OR\s+IGNORE','INSERT',sql,flags=re.I)+' ON CONFLICT DO NOTHING'
    table=re.match(r'^INSERT\s+INTO\s+(\w+)',sql,re.I)
    returning=bool(table and table.group(1) in ID_TABLES)
    if returning: sql+=' RETURNING id'
    return sql,returning

class Cursor:
    def __init__(self,cursor,returning=False):
        self.cursor=cursor;self.lastrowid=None
        if returning:
            r=cursor.fetchone();self.lastrowid=r['id'] if r else None
    def fetchone(self): return self.cursor.fetchone()
    def fetchall(self): return self.cursor.fetchall()
    def __iter__(self): return iter(self.cursor)

class Connection:
    def __init__(self,raw): self.raw=raw
    def execute(self,statement,params=()):
        import psycopg
        sql,returning=postgres_sql(statement)
        try: return Cursor(self.raw.execute(sql,params),returning)
        except psycopg.IntegrityError as exc:
            raise sqlite3.IntegrityError('Violação de integridade do banco.') from exc
    def set_context(self,org,unit,role,actor):
        self.raw.execute("SELECT set_config('prisma.org',%s,true),set_config('prisma.unit',%s,true),set_config('prisma.role',%s,true),set_config('prisma.actor',%s,true),set_config('prisma.worker','0',true)",(str(org),str(unit),str(role),str(actor)))
    def set_system_context(self): self.raw.execute("SELECT set_config('prisma.worker','1',true)")
    def commit(self): self.raw.commit()
    def rollback(self): self.raw.rollback()
    def close(self): self.raw.close()
    def __enter__(self): return self
    def __exit__(self,typ,value,tb):
        try:
            self.raw.rollback() if typ else self.raw.commit()
        finally: self.raw.close()

class PostgresDatabase(Database):
    def __init__(self,url):
        self.url=url;self.path=None
        if not url.startswith(('postgresql://','postgres://')): raise RuleError('DATABASE_URL precisa ser PostgreSQL.')
    def _raw(self):
        import psycopg
        raw=psycopg.connect(self.url,autocommit=False,row_factory=record_factory,prepare_threshold=None,connect_timeout=10)
        raw.execute("SET search_path TO prisma_agenda,pg_catalog")
        raw.execute("SET timezone TO 'UTC'")
        raw.execute("SET statement_timeout TO '30s'")
        raw.execute("SET lock_timeout TO '15s'")
        return raw
    def connect(self):
        raw=self._raw()
        try: raw.execute('SET LOCAL ROLE prisma_agenda_runtime')
        except Exception: raw.close();raise
        return Connection(raw)
    @contextmanager
    def transaction(self):
        c=self.connect()
        try:
            # Consistency across API processes; never hold across external network calls.
            c.raw.execute('SELECT pg_advisory_xact_lock(1347569997,1)')
            yield c;c.commit()
        except Exception:c.rollback();raise
        finally:c.close()
    def migrate(self):
        """Run only with an explicit migration credential, never on a public request."""
        raw=self._raw()
        try:
            raw.execute('SELECT pg_advisory_xact_lock(1347569997,2)')
            existing=raw.execute("SELECT to_regclass('prisma_agenda.schema_version') AS relation").fetchone()['relation']
            if not existing:
                migrations=sorted((ROOT/'supabase/migrations').glob('*_prisma_agenda_private.sql'))
                if len(migrations)!=1: raise RuleError('Migração PostgreSQL inicial ausente ou ambígua.')
                raw.execute(migrations[0].read_text(),prepare=False)
            else:
                version=raw.execute('SELECT version FROM prisma_agenda.schema_version').fetchone()
                if not version or version['version']!=1: raise RuleError('Versão PostgreSQL incompatível.')
            raw.commit()
        except Exception:raw.rollback();raise
        finally:raw.close()
    def seed(self,demo_bookings=False):
        raw=self._raw(); c=Connection(raw)
        try:
            raw.execute('SELECT pg_advisory_xact_lock(1347569997,1)')
            self._seed(c,demo_bookings)
            for table in sorted(ID_TABLES):
                raw.execute(f"SELECT setval(pg_get_serial_sequence('prisma_agenda.{table}','id'),GREATEST(COALESCE((SELECT MAX(id) FROM prisma_agenda.{table}),1),1),EXISTS(SELECT 1 FROM prisma_agenda.{table}))")
            raw.commit()
        except Exception:raw.rollback();raise
        finally:raw.close()
    def backup(self,dest):
        raise RuleError('Para PostgreSQL use pg_dump com URL somente no servidor; consulte docs/SUPABASE.md. Backup SQLite não é compatível.')
