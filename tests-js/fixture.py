import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psycopg
from psycopg import sql
from app.postgres import PostgresDatabase
url=sys.argv[1]
with psycopg.connect(url,autocommit=True) as c:
 for name in ['anon','authenticated']:
  if not c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(name,)).fetchone():c.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(name)))
db=PostgresDatabase(url);db.migrate();db.seed()
raw=db._raw()
raw.execute(next((Path(__file__).resolve().parents[1]/'supabase/migrations').glob('*_hosted_runtime.sql')).read_text(),prepare=False);raw.commit();raw.close()
