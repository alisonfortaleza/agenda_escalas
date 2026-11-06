"""Loopback-only demo HTTP server. Production hosting is deliberately gated."""
import os,json,threading,time,sqlite3,secrets,ipaddress,logging
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from urllib.parse import urlparse,parse_qs
from .db import Database,ROOT
from .service import Service
from .domain import RuleError,require
from datetime import datetime,timezone

class AppServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,service,bootstrap=False):
        self.service=service; self.bootstrap=bootstrap; self.attempts={}; self.attempt_lock=threading.Lock(); super().__init__(address,Handler)

class Handler(BaseHTTPRequestHandler):
    server_version='AgendaLocal/1'
    def log_message(self,*args): pass # Never log CPF, bodies, tokens, query strings.
    def respond(self,status,data,cookie=None):
        body=json.dumps(data,ensure_ascii=False).encode(); self.send_response(status)
        self.headers_secure(); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body)))
        if cookie: self.send_header('Set-Cookie',cookie)
        self.end_headers(); self.wfile.write(body)
    def headers_secure(self):
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Referrer-Policy','no-referrer'); self.send_header('X-Frame-Options','DENY')
        self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
    def do_GET(self): self.dispatch('GET')
    def do_POST(self): self.dispatch('POST')
    def dispatch(self,method):
        try:
            host=self.headers.get('Host',''); parsed_host=urlparse('//'+host).hostname
            require(parsed_host in ('localhost','127.0.0.1','::1'),'Servidor de teste aceita somente acesso local.',403)
            path=urlparse(self.path).path; q=parse_qs(urlparse(self.path).query); svc=self.server.service
            if not path.startswith('/api/'):
                require(method=='GET','Método não permitido.',405)
                filename={'/':'index.html','/app.js':'app.js','/style.css':'style.css'}.get(path)
                require(filename,'Página não encontrada.',404); f=ROOT/'web'/filename; body=f.read_bytes(); self.send_response(200); self.headers_secure()
                self.send_header('Content-Type',{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[filename.split('.')[-1]])
                self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
            d={}
            if method=='POST':
                require(self.headers.get('Origin')==f'http://{host}','Origem não autorizada.',403)
                require(self.headers.get('Content-Type','').startswith('application/json'),'Use JSON.',415)
                size=int(self.headers.get('Content-Length','0')); require(0<size<=250000,'Solicitação muito grande.',413)
                d=json.loads(self.rfile.read(size)); require(isinstance(d,dict),'JSON inválido.')
            if path=='/api/health': self.respond(200,{'status':'ok','mode':'local_test','production':False}); return
            if path=='/api/bootstrap':
                with svc.db.connect() as c: available=bool(c.execute("SELECT 1 FROM users WHERE org=1 AND login='admin' AND password IS NULL").fetchone())
                self.respond(200,{'available':self.server.bootstrap and available}); return
            if path=='/api/login' and method=='POST':
                key=self.client_address[0]; now=time.monotonic()
                with self.server.attempt_lock:
                    previous=[x for x in self.server.attempts.get(key,[]) if now-x<60]; require(len(previous)<15,'Muitas tentativas. Aguarde um minuto.',429); self.server.attempts[key]=previous+[now]
                result=svc.login(int(d.get('org',1)),str(d.get('login','')),str(d.get('password','')),d.get('bootstrap') is True,self.server.bootstrap and ipaddress.ip_address(self.client_address[0]).is_loopback)
                token=result.pop('token'); self.respond(200,result,f'agenda_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'); return
            cookie=SimpleCookie(self.headers.get('Cookie','')); token=cookie.get('agenda_session'); require(token,'Entre para continuar.',401)
            user,session=svc.authenticate(token.value)
            if method=='POST': require(secrets.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']),'Sessão de formulário inválida.',403)
            unit=int(q.get('unit',[user['unit']])[0])
            if path=='/api/session': result={'user':user,'csrf':session['csrf'],'temporary':bool(session['temporary'])}
            elif path=='/api/logout' and method=='POST':
                with svc.db.transaction() as c: c.execute('DELETE FROM sessions WHERE token=?',(token.value,))
                self.respond(200,{'message':'Sessão encerrada.'},'agenda_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'); return
            elif path=='/api/password' and method=='POST': result=svc.set_password(user,d)
            elif path=='/api/state' and method=='GET': result=svc.state(user,unit)
            elif path=='/api/reserve' and method=='POST': result=svc.reserve(user,unit,d)
            elif path=='/api/reservation-action' and method=='POST': result=svc.reservation_action(user,unit,d.pop('id'),d.pop('action'),d)
            elif path=='/api/refund' and method=='POST': result=svc.refund(user,unit,d.pop('id'),d)
            elif path=='/api/availability' and method=='POST': result=svc.availability(user,unit,d)
            elif path=='/api/user' and method=='POST': result=svc.create_user(user,unit,d)
            elif path=='/api/room' and method=='POST': result=svc.create_room(user,unit,d)
            elif path=='/api/people' and method=='POST': result=svc.create_person(user,unit,d)
            elif path=='/api/block' and method=='POST': result=svc.create_block(user,unit,d)
            elif path=='/api/block-resolve' and method=='POST': result=svc.resolve_block(user,unit,d)
            elif path=='/api/unblock' and method=='POST': result=svc.remove_block(user,unit,d['id'])
            elif path=='/api/settings' and method=='POST': result=svc.update_settings(user,unit,d)
            elif path=='/api/reason' and method=='POST': result=svc.save_reason(user,unit,d)
            elif path=='/api/schedules' and method=='GET': result=svc.schedules(user,unit)
            elif path=='/api/schedule' and method=='POST': result=svc.schedule_action(user,unit,d.pop('action'),d)
            elif path=='/api/swap' and method=='POST': result=svc.swap_action(user,unit,d.pop('action'),d)
            elif path=='/api/work' and method=='POST': result=svc.save_work(user,unit,d)
            elif path=='/api/export' and method=='GET':
                svc.role(user,'admin','manager'); result=svc.state(user,unit)
                if user['role']=='manager': result.pop('audit',None)
            else: raise RuleError('Operação não encontrada.',404)
            self.respond(200,result)
        except RuleError as e: self.respond(e.status,{'error':str(e),'details':e.details})
        except sqlite3.IntegrityError: self.respond(409,{'error':'Cadastro, referência ou benefício duplicado. Atualize os dados.'})
        except (ValueError,KeyError,TypeError,json.JSONDecodeError): self.respond(400,{'error':'Dados incompletos ou inválidos.'})
        except Exception:
            logging.exception('Erro interno sem conteúdo de requisição'); self.respond(500,{'error':'Erro interno. Operação não concluída.'})

def main():
    require(os.environ.get('APP_ENV','local')=='local','Publicação bloqueada: esta versão requer revisão de segurança e configuração de produção.')
    if os.environ.get('DATABASE_URL'):
        from .postgres import PostgresDatabase
        db=PostgresDatabase(os.environ['DATABASE_URL'])
        if os.environ.get('MIGRATE_ON_START','0')=='1': db.migrate()
    else:
        db=Database(os.environ.get('DATABASE_PATH',str(ROOT/'data/agenda.sqlite'))); db.migrate()
    if os.environ.get('SEED_DEMO','0')=='1': db.seed(demo_bookings=True)
    svc=Service(db); stop=threading.Event()
    def jobs():
        while not stop.wait(15):
            try: svc.job_tick()
            except Exception: logging.exception('Falha no processamento de pendências')
    threading.Thread(target=jobs,daemon=True).start()
    port=int(os.environ.get('PORT','8765')); server=AppServer(('127.0.0.1',port),svc,os.environ.get('BOOTSTRAP_LOCAL','0')=='1')
    print(f'Agenda de teste: http://127.0.0.1:{port} — somente loopback',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: stop.set(); server.server_close()
if __name__=='__main__': main()
