import sys,os,json,subprocess,tempfile,unittest,secrets,urllib.request
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlsplit,urlunsplit
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
import psycopg
from psycopg import sql
import test_rules
from app.postgres import PostgresDatabase
from app.service import Service
from app.domain import RuleError
base=os.environ.get('PRISMA_PG_TEST_URL','postgresql://postgres@127.0.0.1:55432/postgres');parsed=urlsplit(base)
assert parsed.hostname in ('localhost','127.0.0.1','::1'),'Tests must never target hosted Postgres.'
bridge=subprocess.Popen(['node',str(ROOT/'tests-js/bridge.mjs')],stdout=subprocess.PIPE,text=True,cwd=ROOT)
port=int(bridge.stdout.readline().strip())
class FixtureDatabase(PostgresDatabase):
 def connect(self):
  c=super().connect();c.set_system_context();return c
class NodeService(Service):
 def _call(self,name,*args):
  # Password API takes a user but no unit parameter in the Python contract.
  if name=='set_password':args=(args[0],args[0]['unit'],args[1])
  body=json.dumps({'url':self.db.url,'now':self.now().isoformat(),'method':name,'args':args}).encode()
  request=urllib.request.Request(f'http://127.0.0.1:{port}/',data=body,headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(request,timeout=60) as r:data=json.load(r)
  if 'error' in data:raise RuleError(data['error'],data.get('status',422),data.get('details'))
  return data['result']
for name in ['login','authenticate','job_tick','state','reserve','reservation_action','refund','create_person','create_block','remove_block','update_settings','save_reason','schedules','schedule_action','save_work','resolve_block','swap_action','create_user','create_room','availability','set_password']:
 setattr(NodeService,name,lambda self,*args,_name=name,**kwargs:self._call(_name,*args))
def setup(self):
 self.tmp=tempfile.TemporaryDirectory();self.database_name='prisma_js_'+secrets.token_hex(6)
 with psycopg.connect(base,autocommit=True) as c:
  for name in ['anon','authenticated']:
   if not c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(name,)).fetchone():c.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(name)))
  c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(self.database_name)))
 self.db=FixtureDatabase(urlunsplit(parsed._replace(path='/'+self.database_name)));self.db.migrate();self.db.seed()
 with self.db._raw() as c:c.execute(next((ROOT/'supabase/migrations').glob('*_hosted_runtime.sql')).read_text(),prepare=False)
 self.time=datetime(2026,11,6,12,tzinfo=timezone.utc);self.s=NodeService(self.db,lambda:self.time)
 with self.db.connect() as c:self.users={r['login']:dict(r) for r in c.execute('SELECT * FROM users WHERE org=1 AND unit=1')}
 self.rec=self.users['recepcao'];self.admin=self.users['admin'];self.teacher=self.users['professor']
def teardown(self):
 with psycopg.connect(base,autocommit=True) as c:c.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(self.database_name)))
 self.tmp.cleanup()
test_rules.Fixture.setUp=setup;test_rules.Fixture.tearDown=teardown
for cls,name in [(test_rules.IncidentConfigTests,'test_backup_restore_consistent'),(test_rules.CompletionTests,'test_restore_clears_sessions_and_preserves_password'),(test_rules.IdentityTests,'test_bootstrap_protection'),(test_rules.IdentityTests,'test_password_closes_bootstrap_and_sessions_persistently')]:
 setattr(cls,name,unittest.skip('Local-only/bootstrap or SQLite backup contract; hosted public-mode contracts tested separately.')(getattr(cls,name)))
try:
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_rules))
finally:
 bridge.terminate();bridge.wait(timeout=10)
sys.exit(not result.wasSuccessful())
