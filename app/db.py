import sqlite3, json, hashlib, secrets
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime,timezone
from .domain import default_settings
ROOT=Path(__file__).resolve().parents[1]

def hash_password(p):
    salt=secrets.token_hex(16)
    return salt+':'+hashlib.scrypt(p.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()

def verify_password(p,h):
    if not h: return False
    salt,_=h.split(':')
    return secrets.compare_digest(h,salt+':'+hashlib.scrypt(p.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex())

def synthetic_cpf(n):
    value=f'{900000000+n:09d}'
    for size in (9,10): value+=str((sum(int(value[i])*(size+1-i) for i in range(size))*10)%11%10)
    return value

class Database:
    def __init__(self,path): self.path=str(path)
    def connect(self):
        c=sqlite3.connect(self.path,timeout=20,isolation_level=None); c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON'); c.execute('PRAGMA busy_timeout=20000'); return c
    @contextmanager
    def transaction(self):
        c=self.connect()
        try:
            c.execute('BEGIN IMMEDIATE'); yield c; c.commit()
        except Exception: c.rollback(); raise
        finally: c.close()
    def migrate(self):
        Path(self.path).parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:
            c.execute('PRAGMA journal_mode=WAL'); c.executescript((ROOT/'migrations/001_initial.sql').read_text())
    def seed(self,demo_bookings=False):
        with self.transaction() as c:
            self._seed(c,demo_bookings)
    def _seed(self,c,demo_bookings=False):
        if c.execute('SELECT 1 FROM organizations LIMIT 1').fetchone(): return
        now=datetime.now(timezone.utc).isoformat()
        s=default_settings()
        for org,name in [(1,'Academia Demonstração'),(2,'Outra Academia • isolamento')]: c.execute('INSERT INTO organizations VALUES(?,?)',(org,name))
        for uid,org,name in [(1,1,'Panobianco • Unidade Jardim Demo'),(2,1,'Unidade Horizonte Demo'),(3,2,'Academia Independente Demo')]:
            conf=dict(s)
            if uid==2: conf.update(student_duration=40,external_price=8000,daily_offer=13)
            c.execute('INSERT INTO units VALUES(?,?,?,?,1)',(uid,org,name,json.dumps(conf)))
            c.execute('INSERT INTO config_versions(org,unit,version,settings,created) VALUES(?,?,1,?,?)',(org,uid,json.dumps(conf),now))
            c.execute('INSERT INTO rooms VALUES(?,?,?,?)',(uid,org,uid,'Sala de avaliação 01'))
        people=[(1,'Marina Ribeiro','internal','pe','CREF:PE:DEMO001',None,None),(2,'Rafael Gomes','internal','pe','CREF:PE:DEMO002',None,None),(3,'Beatriz Nunes','internal','pe','CREF:PE:DEMO003',None,None),(4,'Lucas Ferreira','intern',None,None,'52998224725',1),(5,'Camila Souza','external','pe','CREF:PE:DEMO900',None,None),(6,'Helena Costa','external','nutrition','CRN:6:DEMO901',None,None),(7,'Alice Martins','student',None,None,'11144477735',None),(8,'Bruno Almeida','student',None,None,'12345678909',None)]
        for pid,name,kind,prof,reg,cp,tutor in people:
            c.execute('INSERT INTO people(id,org,unit,name,kind,profession,registry,cpf,phone,registration,plan_until,tutor) VALUES(?,1,1,?,?,?,?,?,?,?,?,?)',(pid,name,kind,prof,reg,cp,'81999990000',f'DEMO-{pid}','2099-12-31',tutor))
        for pid in range(9,17):
            intern=pid>=14
            c.execute('INSERT INTO people(id,org,unit,name,kind,profession,registry,cpf,phone,registration,plan_until,tutor) VALUES(?,1,1,?,?,?,?,?,?,?,?,?)',(pid,f'Equipe Demo {chr(65+pid)}','intern' if intern else 'internal',None if intern else 'pe',None if intern else f'CREF:PE:DEMO{pid}',synthetic_cpf(pid) if intern else None,'81999990000',f'DEMO-{pid}','2099-12-31',1 if intern else None))
        # Synthetic CPFs above exist only as algorithm-valid fixtures; never used as real identities.
        for uid,org,unit,person,login,role in [(1,1,1,None,'admin','admin'),(2,1,1,None,'gerente','manager'),(3,1,1,None,'recepcao','reception'),(4,1,1,1,'professor','teacher'),(5,1,1,4,'estagiario','intern'),(6,1,1,2,'professor2','teacher'),(7,1,2,None,'recepcao2','reception'),(8,2,3,None,'admin','admin')]:
            c.execute('INSERT INTO users(id,org,unit,person,login,role,password) VALUES(?,?,?,?,?,?,?)',(uid,org,unit,person,login,role,None if role=='admin' else hash_password('Demo@2026!')))
        for pid in [1,2,3]+list(range(9,17))+[4]:
            times=('08:00','14:00') if pid%3==1 else ('12:00','18:00') if pid%3==2 else ('17:00','23:00')
            if pid in (4,14,15,16): times=('08:00','13:00')
            for wd in range(5): c.execute('INSERT INTO work(org,unit,person,weekday,start,end,valid_from,valid_to,contract_minutes) VALUES(1,1,?,?,?,?,?,?,?)',(pid,wd,*times,'2026-01-01','2099-12-31',1800 if pid in (4,14,15,16) else 2160))
        c.execute("INSERT INTO reasons(org,unit,title) VALUES(1,1,'Exemplo de demonstração — atraso de transporte')")
        c.execute('INSERT INTO notifications(org,unit,message,created) VALUES(1,1,?,?)',('Ambiente fictício: Pix, WhatsApp e registros profissionais não são verificados. Confirme âncora e regras pendentes antes de publicar escalas.',now))
        if demo_bookings:
            from datetime import timedelta
            from zoneinfo import ZoneInfo
            from .domain import iso,local_start
            today=datetime.now(ZoneInfo(s['timezone'])).date()
            monday=today+timedelta(days=(7-today.weekday())%7 or 7)
            saturday=today+timedelta(days=(5-today.weekday())%7 or 7)
            demo=[('student',7,1,monday,'08:00',30),('student',8,1,monday,'09:00',30),('internal',None,2,monday,'18:00',60),('external',None,5,saturday,'08:00',60)]
            for category,student,professional,day,time,duration in demo:
                start=local_start(day.isoformat(),time,s); end=start+timedelta(minutes=duration)
                snap={'duration':duration,'price':4000 if category=='external' else 0,'retention':50,'penalty_hours':48,'version':1,'category':category,'accepted':category=='external','policy':'DADOS FICTÍCIOS: retenção de 50%, reembolso manual.','use_deadline_minutes':None,'professional_no_show_confirmed':False}
                cur=c.execute('INSERT INTO reservations(org,unit,room,person,student,category,start,end,status,payment,snapshot,expires,created,operator) VALUES(1,1,1,?,?,?,?,?,?,?,?,?,?,3)',(professional,student,category,iso(start),iso(end),'awaiting_payment' if category=='external' else 'confirmed','pending' if category=='external' else 'not_applicable',json.dumps(snap),iso(datetime.now(timezone.utc)+timedelta(minutes=10)) if category=='external' else None,now))
                if student:
                    identity=c.execute('SELECT cpf FROM people WHERE id=?',(student,)).fetchone()[0]
                    c.execute('INSERT INTO benefits VALUES(1,1,?,?,?)',(identity,day.strftime('%Y-%m'),cur.lastrowid))
                c.execute("INSERT INTO audit(org,unit,actor,action,entity,data,created) VALUES(1,1,0,'demo_fixture',?,?,?)",(str(cur.lastrowid),json.dumps({'fixture':True}),now))
    def backup(self,dest):
        with self.connect() as source, sqlite3.connect(dest) as target: source.backup(target)
