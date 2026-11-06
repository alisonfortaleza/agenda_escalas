import json, secrets, sqlite3, calendar
from datetime import datetime,timedelta,date,timezone
from zoneinfo import ZoneInfo
from .domain import *
from .db import hash_password, verify_password

SCHEDULE_ROLES=('admin','manager','teacher','intern')
FINANCE_ROLES=('admin','manager','reception')
ACTIVE=('confirmed','awaiting_payment','no_show')

def obj(row): return dict(row) if row is not None else None

def rows(c,sql,args=()): return [dict(r) for r in c.execute(sql,args)]

class Service:
    def __init__(self,db,now=None): self.db=db; self._clock=now or (lambda:datetime.now(timezone.utc))
    def now(self): return self._clock().astimezone(timezone.utc)
    def scope(self,c,user,unit=None):
        unit=int(unit or user['unit'])
        require(user['role']=='admin' or unit==user['unit'],'Unidade não autorizada.',403)
        if hasattr(c,'set_context'): c.set_context(user['org'],unit,user['role'],user['id'])
        u=obj(c.execute('SELECT * FROM units WHERE id=? AND org=?',(unit,user['org'])).fetchone())
        require(u,'Unidade não autorizada.',403); u['settings']=json.loads(u['settings']); return u
    def entity(self,c,table,id,u):
        require(table in ('people','rooms','reservations','refunds','schedules','swaps','blocks','reasons','users'),'Entidade inválida.')
        r=obj(c.execute(f'SELECT * FROM {table} WHERE id=? AND org=? AND unit=?',(int(id),u['org'],u['id'])).fetchone())
        require(r,'Registro não encontrado nesta unidade.',404); return r
    def role(self,user,*roles): require(user['role'] in roles,'Seu perfil não permite esta operação.',403)
    def audit(self,c,user,u,action,entity,data):
        c.execute('INSERT INTO audit(org,unit,actor,action,entity,data,created) VALUES(?,?,?,?,?,?,?)',(u['org'],u['id'],user['id'],action,str(entity),json.dumps(data,ensure_ascii=False),iso(self.now())))
    def login(self,org,login,password,bootstrap=False,protected=False):
        with self.db.transaction() as c:
            u=obj(c.execute('SELECT * FROM users WHERE org=? AND login=?',(org,login)).fetchone())
            require(u,'Acesso inválido.',401)
            if bootstrap: require(protected and u['role']=='admin' and u['password'] is None,'Acesso de implantação indisponível.',403)
            else: require(verify_password(password,u['password']),'Acesso inválido.',401)
            token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(24)
            c.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?)',(token,u['id'],csrf,iso(self.now()+timedelta(hours=8)),int(bootstrap),u['generation']))
            return {'token':token,'csrf':csrf,'user':{k:v for k,v in u.items() if k!='password'},'temporary':bootstrap}
    def authenticate(self,token):
        with self.db.connect() as c:
            s=obj(c.execute('SELECT * FROM sessions WHERE token=?',(token,)).fetchone()); require(s and instant(s['expires'])>self.now(),'Sessão encerrada. Entre novamente.',401)
            u=obj(c.execute('SELECT * FROM users WHERE id=?',(s['user'],)).fetchone()); require(u and s['generation']==u['generation'],'Sessão encerrada.',401)
            if hasattr(c,'set_context'): c.set_context(u['org'],u['unit'],u['role'],u['id'])
            if u['person']:
                p=c.execute('SELECT active FROM people WHERE id=?',(u['person'],)).fetchone(); require(p and p['active'],'Vínculo inativo.',403)
            u.pop('password',None); return u,s
    def set_password(self,user,data):
        p=data.get('password',''); require(p==data.get('confirmation') and len(p)>=10,'As senhas devem coincidir e ter ao menos 10 caracteres.')
        with self.db.transaction() as c:
            u=obj(c.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone())
            if u['password']: require(verify_password(data.get('current',''),u['password']),'Senha atual inválida.',403)
            c.execute('UPDATE users SET password=?,generation=generation+1 WHERE id=?',(hash_password(p),user['id']))
            c.execute('DELETE FROM sessions WHERE user=?',(user['id'],))
            unit=self.scope(c,user); self.audit(c,user,unit,'password_defined',user['id'],{})
        return {'message':'Senha salva. Entre novamente com a nova senha.'}
    def identity(self,p): return p['registry'] or ('CPF:'+p['cpf'] if p['cpf'] else 'PERSON:'+str(p['id']))
    def settings_for(self,c,u,day):
        found=rows(c,'SELECT settings,version FROM config_versions WHERE unit=? AND org=? ORDER BY version DESC',(u['id'],u['org']))
        for v in found:
            s=json.loads(v['settings'])
            if s['effective_from']<=day: return {**s,'_version':v['version']}
        return u['settings']
    def work_intervals(self,c,u,person,day,include_schedule=True):
        out=[]
        for w in rows(c,'SELECT * FROM work WHERE org=? AND unit=? AND person=? AND weekday=? AND valid_from<=? AND valid_to>=?',(u['org'],u['id'],person,day.weekday(),day.isoformat(),day.isoformat())):
            out.append((local_start(day.isoformat(),w['start'],u['settings']),local_start(day.isoformat(),w['end'],u['settings'])))
        if include_schedule:
            # Latest published version per month. Friday adjustments replace regular work.
            for sc in rows(c,"SELECT * FROM schedules WHERE org=? AND unit=? AND status='published' AND id IN (SELECT MAX(id) FROM schedules WHERE org=? AND unit=? AND status='published' GROUP BY month)",(u['org'],u['id'],u['org'],u['id'])):
                for a in json.loads(sc['assignments']):
                    if a['person']==person and a['date']==day.isoformat():
                        if a.get('adjustment') or a.get('off'): out=[]
                        if not a.get('off'): out.append((local_start(a['date'],a['start'],u['settings']),local_start(a['date'],a['end'],u['settings'])))
        return out
    def available(self,c,u,room,person,tutor,start,end,exclude=None):
        for r in rows(c,"SELECT * FROM reservations WHERE org=? AND unit=? AND status IN ('confirmed','awaiting_payment','no_show') AND start<? AND end>?",(u['org'],u['id'],iso(end),iso(start))):
            if r['id']==exclude: continue
            require(r['room']!=room,'Sala ocupada nesse intervalo.',409)
            actors={person,tutor}-{None}; existing={r['person'],r['tutor']}-{None}
            require(not actors.intersection(existing),'Profissional ou tutor indisponível neste horário.',409)
        for b in rows(c,'SELECT * FROM blocks WHERE org=? AND unit=? AND start<? AND end>?',(u['org'],u['id'],iso(end),iso(start))):
            require(not (b['room']==room or b['person'] in ({person,tutor}-{None})),'Sala ou profissional bloqueado: '+b['reason'],409)
    def validate_booking(self,c,user,u,data,exclude=None,exception=False,snapshot=None):
        category=data['category']; require(category in ('student','internal','external'),'Categoria inválida.')
        room=self.entity(c,'rooms',data['room'],u); p=self.entity(c,'people',data['person'],u); require(p['active'],'Profissional inativo.')
        start=instant(data['start']).astimezone(ZoneInfo(u['settings']['timezone'])); s=self.settings_for(c,u,start.date().isoformat())
        duration=snapshot['duration'] if snapshot else s[category+'_duration']; end=start+timedelta(minutes=duration)
        require(start>self.now(),'Escolha um horário futuro.'); require(start.second==0 and start.minute%10==0,'Use inícios na grade de 10 minutos.')
        hours=opening(start.date(),s); require(hours is not None,'Unidade fechada nesta data.')
        require(start.date()==end.date() and minutes(hours[0])<=start.hour*60+start.minute and end.hour*60+end.minute<=minutes(hours[1]),'Atendimento precisa terminar dentro do funcionamento.')
        tutor=None; student=None
        if category=='external':
            self.role(user,'reception'); require(p['kind']=='external','Selecione um profissional externo.')
            require(start.weekday()>=5 or s['external_weekdays'],'Dias úteis bloqueados para externos.')
            require(data.get('accepted') is True,'Registre o aceite da política antes de continuar.')
            if snapshot is None:
                require(data.get('accepted_terms')=={'duration':duration,'price':s['external_price'],'retention':s['retention']},'Os termos mudaram. Reabra a reserva e informe a política atual ao profissional.',409)
        else:
            require(p['kind'] in ('internal','intern'),'Selecione um profissional interno.')
            if category=='internal':
                self.role(user,'teacher','intern','reception')
                if user['role'] in ('teacher','intern'): require(user['person']==p['id'] or (p['kind']=='intern' and user['person']==p['tutor'] and data.get('tutor_approved') is True),'Reserve apenas para si ou aprove seu orientando.',403)
                penalty=c.execute('SELECT end FROM penalties WHERE org=? AND unit=? AND identity=? AND end>?',(u['org'],u['id'],self.identity(p),iso(self.now()))).fetchone()
                require(not penalty,'Profissional com penalidade ativa de 48 horas.')
                require(not any(overlap(start,end,a,b) for a,b in self.work_intervals(c,u,p['id'],start.date())),'Profissional indisponível neste horário.')
            else:
                self.role(user,*('reception','admin') if exception else ('reception',))
                student=self.entity(c,'people',data['student'],u); require(student['kind']=='student' and student['active'],'Aluno inativo ou inválido.'); cpf(student['cpf'])
                require(student['plan_until']>=start.date().isoformat(),'Plano sem vigência na data escolhida.')
                require(start.date().isoformat() not in s['holidays'],'Não há avaliações de alunos em feriados.')
                if not exception:
                    today=self.now().astimezone(ZoneInfo(s['timezone'])).date(); monday=today+timedelta(days=7-today.weekday())
                    require(today.weekday()==4,'Avaliações Platinum só podem ser marcadas na sexta-feira.')
                    require(monday<=start.date()<=monday+timedelta(days=3),'Escolha segunda a quinta da semana imediatamente seguinte.')
                    require(start.strftime('%H:%M') in slots(s),'Horário fora da oferta de alunos.')
                require(any(a<=start and end<=b for a,b in self.work_intervals(c,u,p['id'],start.date())),'Profissional indisponível neste horário.')
                existing=c.execute('SELECT reservation FROM benefits WHERE org=? AND unit=? AND cpf=? AND month=?',(u['org'],u['id'],student['cpf'],start.strftime('%Y-%m'))).fetchone()
                require(not existing or existing['reservation']==exclude,'CPF já tem benefício comprometido neste mês.',409)
                count=c.execute("SELECT COUNT(*) FROM reservations WHERE org=? AND unit=? AND room=? AND category='student' AND substr(start,1,10)=? AND status!='cancelled' AND id!=?",(u['org'],u['id'],room['id'],iso(start)[:10],exclude or -1)).fetchone()[0]
                require(exception or count<s['daily_offer'],'Oferta diária esgotada.')
            if p['kind']=='intern':
                require(s['supervision_confirmed'] and s['intern_penalty_confirmed'],'Tutoria e política de estágio pendentes de confirmação administrativa.')
                require(p['tutor'],'Estagiário sem tutor.'); tutor=self.entity(c,'people',p['tutor'],u)
                require(tutor['active'] and tutor['kind']=='internal' and tutor['registry'],'Tutor inválido.')
                if category=='internal': require(not any(overlap(start,end,a,b) for a,b in self.work_intervals(c,u,tutor['id'],start.date())),'Tutor indisponível neste horário.')
                require(data.get('tutor_approved') is True and user['person']==tutor['id'],'Reserva do estagiário exige aprovação autenticada do tutor.',403)
        if category!='student':
            windows=[(local_start(start.date().isoformat(),a,s),local_start(start.date().isoformat(),b,s)) for a,b in s['windows']] if start.weekday()<4 and start.date().isoformat() not in s['holidays'] else []
            if s[category+'_sharing']=='exclusive': require(not any(overlap(start,end,a,b) for a,b in windows),'Janela exclusiva de alunos.')
            if not s[category+'_outside']: require(any(a<=start and end<=b for a,b in windows),'Uso fora das janelas não autorizado.')
        self.available(c,u,room['id'],p['id'],tutor['id'] if tutor else None,start,end,exclude)
        snap=snapshot or {'duration':duration,'price':s['external_price'] if category=='external' else 0,'retention':s['retention'],'penalty_hours':s['penalty_hours'],'version':s.get('_version',u['version']),'category':category,'accepted':data.get('accepted',False),'accepted_by':user['id'],'accepted_at':iso(self.now()),'policy':'Cancelamento/falta: retenção percentual do valor pago; devolução manual.','professional_no_show_confirmed':s['professional_no_show_confirmed'],'use_deadline_minutes':s['use_deadline_minutes']}
        return start,end,p,student,tutor,snap,s
    def reserve(self,user,unit,data):
        with self.db.transaction() as c:
            u=self.scope(c,user,unit); self.jobs(c,u); start,end,p,student,tutor,snap,s=self.validate_booking(c,user,u,data)
            paid=snap['price']>0; status='awaiting_payment' if paid else 'confirmed'
            cur=c.execute('INSERT INTO reservations(org,unit,room,person,student,tutor,category,start,end,status,payment,snapshot,expires,created,operator) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(u['org'],u['id'],data['room'],p['id'],student['id'] if student else None,tutor['id'] if tutor else None,data['category'],iso(start),iso(end),status,'pending' if paid else 'not_applicable',json.dumps(snap),iso(self.now()+timedelta(minutes=s['hold_minutes'])) if paid else None,iso(self.now()),user['id']))
            rid=cur.lastrowid
            if student: c.execute('INSERT INTO benefits VALUES(?,?,?,?,?)',(u['org'],u['id'],student['cpf'],start.strftime('%Y-%m'),rid))
            self.audit(c,user,u,'reserve',rid,{'category':data['category'],'snapshot':snap})
            return {'id':rid,'status':status,'message':'Aguardando conferência manual do Pix.' if paid else 'Reserva confirmada.'}
    def penalty(self,c,u,r,reason,at=None):
        p=self.entity(c,'people',r['person'],u); snap=json.loads(r['snapshot']); at=at or self.now()
        c.execute('INSERT OR IGNORE INTO penalties(org,unit,identity,reservation,start,end,reason) VALUES(?,?,?,?,?,?,?)',(u['org'],u['id'],self.identity(p),r['id'],iso(at),iso(at+timedelta(hours=snap['penalty_hours'])),reason))
    def refund_due(self,c,u,r,academy=False):
        pay=c.execute('SELECT * FROM payments WHERE reservation=? AND org=? AND unit=?',(r['id'],u['org'],u['id'])).fetchone()
        if pay:
            snap=json.loads(r['snapshot']); retained=0 if academy else pay['amount']*snap['retention']//100
            c.execute('INSERT OR IGNORE INTO refunds(org,unit,reservation,amount,retained,created) VALUES(?,?,?,?,?,?)',(u['org'],u['id'],r['id'],pay['amount']-retained,retained,iso(self.now())))
            c.execute("UPDATE reservations SET payment='refund_pending' WHERE id=?",(r['id'],))
    def jobs(self,c,u):
        now=iso(self.now())
        for r in rows(c,"SELECT * FROM reservations WHERE org=? AND unit=? AND status IN ('confirmed','awaiting_payment')",(u['org'],u['id'])):
            action=None
            if r['status']=='awaiting_payment' and r['expires']<=now:
                c.execute("UPDATE reservations SET status='expired' WHERE id=?",(r['id'],)); action='hold_expired'
            elif r['status']=='confirmed' and r['category']=='student' and r['presence']=='pendente' and self.now()>instant(r['start'])+timedelta(minutes=5):
                c.execute("UPDATE reservations SET status='no_show',presence='faltou' WHERE id=?",(r['id'],)); action='student_no_show'
            elif r['status']=='confirmed' and r['category']!='student':
                snap=json.loads(r['snapshot']); deadline=snap.get('use_deadline_minutes')
                if deadline is not None and snap.get('professional_no_show_confirmed') and not r['used'] and self.now()>instant(r['end'])+timedelta(minutes=deadline):
                    c.execute("UPDATE reservations SET status='no_show' WHERE id=?",(r['id'],))
                    if r['category']=='internal': self.penalty(c,u,r,'Uso não confirmado',instant(r['end'])+timedelta(minutes=deadline))
                    else: self.refund_due(c,u,r)
                    action='professional_no_show'
            if action:
                self.audit(c,{'id':0},u,action,r['id'],{})
                c.execute('INSERT INTO notifications(org,unit,message,created) VALUES(?,?,?,?)',(u['org'],u['id'],f'Reserva #{r["id"]}: {action}',now))
    def job_tick(self):
        with self.db.transaction() as c:
            if hasattr(c,'set_system_context'): c.set_system_context()
            c.execute('DELETE FROM sessions WHERE expires<=?',(iso(self.now()),))
            for raw in rows(c,'SELECT * FROM units'):
                raw['settings']=json.loads(raw['settings']); self.jobs(c,raw)
    def reservation_action(self,user,unit,rid,action,data):
        with self.db.transaction() as c:
            u=self.scope(c,user,unit); self.jobs(c,u); r=self.entity(c,'reservations',rid,u)
            own=user.get('person') in {r['person'],r['tutor']}-{None}
            def operational(): require(user['role'] in ('admin','manager','reception') or own,'Só o responsável pode alterar esse atendimento.',403)
            if action=='pay':
                self.role(user,'admin','reception'); require(r['category']=='external','Reserva sem cobrança.')
                require(r['status'] in ('awaiting_payment','expired'),'Reserva não aguarda pagamento.',409)
                reference=str(data.get('reference','')).strip(); require(len(reference)>=4,'Informe referência de conciliação com ao menos 4 caracteres.')
                amount=data.get('amount'); snap=json.loads(r['snapshot']); require(isinstance(amount,int) and amount==snap['price'],'Valor divergente. Conciliação necessária.')
                require(not c.execute('SELECT 1 FROM payments WHERE org=? AND unit=? AND reference=?',(u['org'],u['id'],reference)).fetchone(),'Referência já conciliada.',409)
                if r['status']=='expired':
                    require(instant(r['start'])>self.now(),'Pagamento após o início exige resolução e devolução manual.')
                    self.validate_booking(c,user,u,{'category':r['category'],'room':r['room'],'person':r['person'],'start':r['start'],'accepted':True},exclude=r['id'],snapshot=snap)
                c.execute('INSERT INTO payments(org,unit,reservation,amount,reference,created,operator) VALUES(?,?,?,?,?,?,?)',(u['org'],u['id'],rid,amount,reference,iso(self.now()),user['id']))
                c.execute("UPDATE reservations SET status='confirmed',payment='confirmed',expires=NULL WHERE id=?",(rid,))
            elif action=='cancel':
                operational(); require(r['status'] in ('confirmed','awaiting_payment'),'Reserva não pode ser cancelada neste estado.',409)
                require(self.now()<instant(r['end']),'Reserva encerrada exige correção auditada, não cancelamento comum.')
                reason=str(data.get('reason','')).strip(); require(reason,'Informe o motivo.')
                academy=data.get('academy') is True
                if academy: self.role(user,'admin','reception')
                c.execute("UPDATE reservations SET status='cancelled' WHERE id=?",(rid,))
                if r['category']=='internal' and not academy: self.penalty(c,u,r,'Cancelamento do profissional')
                if r['category']=='external': self.refund_due(c,u,r,academy)
                # Student benefit remains claimed, including academy cancellation: use relocation instead.
                require(not(academy and r['category']=='student'),'Use realocação por imprevisto para preservar o benefício do aluno.')
            elif action in ('whatsapp','presence','training','use'):
                operational(); require(r['status'] in ('confirmed','no_show'),'Atendimento inativo.',409)
                if action=='whatsapp': c.execute('UPDATE reservations SET whatsapp=1 WHERE id=?',(rid,))
                elif action=='presence':
                    require(r['presence']!='faltou','Após cinco minutos, somente recepção pode justificar o atraso.')
                    c.execute("UPDATE reservations SET presence='compareceu' WHERE id=?",(rid,))
                elif action=='training':
                    self.role(user,'teacher','admin'); require(own or user['role']=='admin','Somente responsável/tutor.',403)
                    p=self.entity(c,'people',r['person'],u); require(p['profession']!='nutrition','Treino não se aplica à Nutrição.')
                    require(r['presence']=='compareceu','Registre primeiro o comparecimento.'); c.execute('UPDATE reservations SET training=1 WHERE id=?',(rid,))
                else:
                    require(r['category']!='student' and instant(r['end'])<=self.now(),'Confirme uso particular após o término.')
                    c.execute('UPDATE reservations SET used=1 WHERE id=?',(rid,))
            elif action=='justify':
                self.role(user,'reception'); require(r['category']=='student' and r['presence']=='faltou','Não há falta automática para corrigir.')
                reason=self.entity(c,'reasons',data.get('reason_id',0),u); require(reason['active'],'Motivo inativo.')
                require(not reason['requires_detail'] or str(data.get('detail','')).strip(),'Informe complemento do motivo.')
                occurred=instant(data.get('occurred','')); require(instant(r['start'])<=occurred<=self.now() and occurred<instant(r['end']),'Presença efetiva deve caber no intervalo original e não estar no futuro.')
                require(data.get('actually_attended') is True,'Confirme o atendimento efetivamente ocorrido.')
                c.execute("UPDATE reservations SET presence='compareceu',status='confirmed' WHERE id=?",(rid,)); data={**data,'reason_snapshot':reason}
            else: raise RuleError('Ação desconhecida.',404)
            self.audit(c,user,u,action,rid,data); return {'message':'Operação registrada.'}
    def refund(self,user,unit,id,data):
        self.role(user,'admin','reception')
        with self.db.transaction() as c:
            u=self.scope(c,user,unit); r=self.entity(c,'refunds',id,u)
            require(r['status']!='processed','Devolução já registrada.',409)
            ref=str(data.get('reference','')).strip(); require(ref and data.get('amount')==r['amount'],'Informe referência e valor exato da devolução efetiva.')
            require(data.get('actually_refunded') is True,'Confirme a devolução efetivamente realizada.')
            require(not c.execute('SELECT 1 FROM refunds WHERE org=? AND unit=? AND reference=?',(u['org'],u['id'],ref)).fetchone(),'Referência de devolução duplicada.',409)
            c.execute("UPDATE refunds SET status='processed',reference=?,operator=? WHERE id=?",(ref,user['id'],id))
            c.execute("UPDATE reservations SET payment=? WHERE id=?",('fully_refunded' if r['retained']==0 else 'partially_refunded',r['reservation']))
            self.audit(c,user,u,'refund_recorded',id,{'amount':r['amount'],'reference':ref}); return {'message':'Devolução manual registrada.'}
    def create_person(self,user,unit,d):
        with self.db.transaction() as c:
            u=self.scope(c,user,unit); self.role(user,'admin','reception'); kind=d.get('kind'); require(kind in ('student','external','internal','intern'),'Vínculo inválido.')
            if user['role']=='reception': require(kind in ('student','external') and not d.get('login'),'Recepção cadastra alunos e externos sem login.',403)
            name=normalize_name(d.get('name','')); ph=phone(d.get('phone','')); cp=cpf(d['cpf']) if kind in ('student','intern') else None
            prof=d.get('profession') if kind not in ('student','intern') else None; registry=None; tutor=None
            if kind in ('external','internal'):
                require(prof in ('pe','nutrition'),'Escolha Personal ou Nutricionista.'); council='CREF' if prof=='pe' else 'CRN'
                number=str(d.get('number','')).strip().upper(); region=str(d.get('region','')).strip().upper()
                require(re.fullmatch(r'[A-Z0-9\-]{2,24}',number) and re.fullmatch(r'[A-Z0-9]{1,8}',region),f'Preencha número e região do {council}.')
                registry=f'{council}:{region}:{number}'
            if kind=='intern':
                t=self.entity(c,'people',d.get('tutor',0),u); require(t['kind']=='internal' and t['active'] and t['registry'] and t['profession']=='pe','Tutor deve ser interno ativo de Educação Física.'); tutor=t['id']
            cur=c.execute('INSERT INTO people(org,unit,name,kind,profession,registry,cpf,phone,registration,plan_until,tutor) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(u['org'],u['id'],name,kind,prof,registry,cp,ph,d.get('registration',''),d.get('plan_until','2099-12-31'),tutor))
            self.audit(c,user,u,'person_created',cur.lastrowid,{'kind':kind}); return {'id':cur.lastrowid,'message':'Cadastro salvo. Registro profissional não verificado no conselho.'}
    def create_block(self,user,unit,d):
        with self.db.transaction() as c:
            u=self.scope(c,user,unit); self.role(user,'admin','reception','teacher'); start,end=instant(d['start']),instant(d['end']); reason=str(d.get('reason','')).strip()
            require(start<end and reason,'Informe intervalo e motivo do bloqueio.')
            room=d.get('room'); person=d.get('person'); require(bool(room)!=bool(person),'Escolha sala OU profissional.')
            if room: self.entity(c,'rooms',room,u)
            if person: self.entity(c,'people',person,u)
            if user['role']=='teacher': require(person==user['person'] and not room,'Professor bloqueia apenas a própria disponibilidade.',403)
            affected=[r for r in rows(c,"SELECT * FROM reservations WHERE org=? AND unit=? AND status IN ('confirmed','awaiting_payment','no_show') AND start<? AND end>?",(u['org'],u['id'],iso(end),iso(start))) if (room and r['room']==room) or (person and person in (r['person'],r['tutor']))]
            require(not affected,'Há atendimentos afetados. Resolva por manutenção/realocação antes de bloquear.',409,{'affected':[r['id'] for r in affected]})
            cur=c.execute('INSERT INTO blocks(org,unit,room,person,start,end,reason,operator,origin) VALUES(?,?,?,?,?,?,?,?,?)',(u['org'],u['id'],room,person,iso(start),iso(end),reason,user['id'],'admin' if user['role']=='admin' else 'operational'))
            self.audit(c,user,u,'block_created',cur.lastrowid,{'reason':reason}); return {'message':'Bloqueio registrado.'}
    def remove_block(self,user,unit,id):
        with self.db.transaction() as c:
            u=self.scope(c,user,unit); b=self.entity(c,'blocks',id,u); self.role(user,'admin','reception','teacher')
            if user['role']=='teacher': require(b['person']==user['person'] and b['operator']==user['id'],'Bloqueio não autorizado.',403)
            if user['role']=='reception': require(b['origin']=='operational','Bloqueio administrativo.',403)
            c.execute('DELETE FROM blocks WHERE id=?',(id,)); self.audit(c,user,u,'block_removed',id,b); return {'message':'Bloqueio retirado.'}
    def update_settings(self,user,unit,d):
        self.role(user,'admin')
        with self.db.transaction() as c:
            u=self.scope(c,user,unit); require(d.get('version')==u['version'],'Configuração alterada por outra sessão. Recarregue.',409)
            s={**u['settings'],**d['settings']}; validate_settings(s)
            require(s['effective_from']>=self.now().astimezone(ZoneInfo(s['timezone'])).date().isoformat(),'Vigência deve ser hoje ou futura.')
            affected=[]
            for r in rows(c,"SELECT * FROM reservations WHERE org=? AND unit=? AND status IN ('confirmed','awaiting_payment','no_show') AND start>?",(u['org'],u['id'],iso(self.now()))):
                start=instant(r['start']).astimezone(ZoneInfo(s['timezone'])); end=instant(r['end']).astimezone(ZoneInfo(s['timezone']))
                if start.date().isoformat()<s['effective_from']: continue
                hours=opening(start.date(),s)
                if not hours or start.hour*60+start.minute<minutes(hours[0]) or end.hour*60+end.minute>minutes(hours[1]) or (r['category']=='external' and start.weekday()<5 and not s['external_weekdays']) or (r['category']=='student' and (start.date().isoformat() in s['holidays'] or start.strftime('%H:%M') not in slots(s))): affected.append(r['id'])
                if r['category']=='student':
                    count=c.execute("SELECT COUNT(*) FROM reservations WHERE unit=? AND room=? AND category='student' AND substr(start,1,10)=? AND status!='cancelled'",(u['id'],r['room'],r['start'][:10])).fetchone()[0]
                    if count>s['daily_offer']: affected.append(r['id'])
            require(not affected,'Alteração afeta reservas. Resolva os conflitos antes de publicar.',409,{'affected':list(set(affected))})
            published=c.execute("SELECT 1 FROM schedules WHERE org=? AND unit=? AND status='published'",(u['org'],u['id'])).fetchone()
            require(not published or all(s[k]==u['settings'][k] for k in ('anchor','holidays','opening')),'Mudança de calendário/âncora exige revisão das escalas publicadas; fluxo pendente nesta versão.',409)
            version=u['version']+1
            c.execute('UPDATE units SET settings=?,version=? WHERE id=?',(json.dumps(s),version,u['id']))
            c.execute('INSERT INTO config_versions(org,unit,version,settings,created) VALUES(?,?,?,?,?)',(u['org'],u['id'],version,json.dumps(s),iso(self.now())))
            self.audit(c,user,u,'settings_version',version,{'before':u['settings'],'after':s}); return {'message':f'Configuração v{version} salva.'}
    def save_reason(self,user,unit,d):
        self.role(user,'admin','manager')
        with self.db.transaction() as c:
            u=self.scope(c,user,unit); title=str(d.get('title','')).strip(); require(title,'Informe o motivo.')
            if d.get('id'):
                self.entity(c,'reasons',d['id'],u); c.execute('UPDATE reasons SET title=?,active=?,requires_detail=? WHERE id=?',(title,int(bool(d.get('active',True))),int(bool(d.get('requires_detail',True))),d['id']))
            else: c.execute('INSERT INTO reasons(org,unit,title,requires_detail) VALUES(?,?,?,?)',(u['org'],u['id'],title,int(bool(d.get('requires_detail',True)))))
            self.audit(c,user,u,'reason_saved',d.get('id','new'),d); return {'message':'Motivo salvo; usos anteriores preservados na auditoria.'}
    def state(self,user,unit,day=None):
        with self.db.transaction() as c:
            u=self.scope(c,user,unit); self.jobs(c,u)
            result={'user':user,'unit':u,'units':rows(c,'SELECT id,name FROM units WHERE org=?',(user['org'],)) if user['role']=='admin' else [{'id':u['id'],'name':u['name']}], 'rooms':rows(c,'SELECT * FROM rooms WHERE org=? AND unit=?',(u['org'],u['id']))}
            ps=rows(c,'SELECT * FROM people WHERE org=? AND unit=? ORDER BY name',(u['org'],u['id']))
            if user['role'] in ('teacher','intern'):
                referenced={r['student'] for r in c.execute('SELECT student FROM reservations WHERE org=? AND unit=?',(u['org'],u['id']))}
                for p in ps:
                    if p['kind']!='student' or p['id'] not in referenced:
                        p.pop('cpf',None);p.pop('phone',None)
            result['people']=ps
            reservations=rows(c,'SELECT * FROM reservations WHERE org=? AND unit=? ORDER BY start',(u['org'],u['id']))
            for r in reservations:
                snap=json.loads(r.pop('snapshot'))
                if user['role'] in FINANCE_ROLES: r['terms']=snap
                else:
                    r['terms']={'duration':snap['duration']}; r.pop('payment',None); r.pop('operator',None)
            result['reservations']=reservations
            result['blocks']=rows(c,'SELECT * FROM blocks WHERE org=? AND unit=?',(u['org'],u['id']))
            result['reasons']=rows(c,'SELECT * FROM reasons WHERE org=? AND unit=?',(u['org'],u['id']))
            result['penalties']=rows(c,'SELECT * FROM penalties WHERE org=? AND unit=?'+(' AND identity=?' if user.get('person') and user['role'] not in FINANCE_ROLES else ''),(u['org'],u['id'],self.identity(self.entity(c,'people',user['person'],u))) if user.get('person') and user['role'] not in FINANCE_ROLES else (u['org'],u['id']))
            result['notifications']=rows(c,'SELECT * FROM notifications WHERE org=? AND unit=? ORDER BY id DESC LIMIT 20',(u['org'],u['id'])) if user['role'] in FINANCE_ROLES else []
            if user['role'] in FINANCE_ROLES:
                for table in ('payments','refunds'): result[table]=rows(c,f'SELECT * FROM {table} WHERE org=? AND unit=?',(u['org'],u['id']))
            if user['role']=='admin': result['audit']=rows(c,'SELECT * FROM audit WHERE org=? AND unit=? ORDER BY id DESC LIMIT 200',(u['org'],u['id']))
            result['capacity']={'theoretical':capacity(u['settings']),'offered':u['settings']['daily_offer'],'weekly':4*u['settings']['daily_offer'],'starts':slots(u['settings'])}
            return result
    def schedules(self,user,unit):
        self.role(user,*SCHEDULE_ROLES)
        with self.db.connect() as c:
            u=self.scope(c,user,unit); result=[]; current=self.now().astimezone(ZoneInfo(u['settings']['timezone'])).strftime('%Y-%m')
            for sc in rows(c,'SELECT * FROM schedules WHERE org=? AND unit=? ORDER BY id DESC',(u['org'],u['id'])):
                if user['role']!='admin' and sc['status']!='published': continue
                sc['assignments']=[{**a,'_index':i} for i,a in enumerate(json.loads(sc['assignments']))]; sc['errors']=json.loads(sc['errors'])
                if user['role']!='admin': sc['assignments']=[a for a in sc['assignments'] if a['date'].startswith(current)]
                for a in sc['assignments']: a['cycle']=cycle(date.fromisoformat(a['date']),date.fromisoformat(sc['anchor']))
                result.append(sc)
            return {'schedules':result,'work':rows(c,'SELECT * FROM work WHERE org=? AND unit=?',(u['org'],u['id'])),'swaps':rows(c,'SELECT * FROM swaps WHERE org=? AND unit=?',(u['org'],u['id']))}
    def schedule_action(self,user,unit,action,d):
        from .scheduling import generate,validate_schedule
        self.role(user,'admin')
        with self.db.transaction() as c:
            u=self.scope(c,user,unit)
            if action=='generate':
                reference=date.fromisoformat(d.get('date',self.now().astimezone(ZoneInfo(u['settings']['timezone'])).date().isoformat()))
                a,errors=generate(self,c,u,reference)
                root=date.fromisoformat(u['settings']['anchor']); cycle_start=root+timedelta(days=((reference-root).days//84)*84)
                cur=c.execute("INSERT INTO schedules(org,unit,status,month,anchor,assignments,errors,created) VALUES(?,?,'draft',?,?,?,?,?)",(u['org'],u['id'],cycle_start.strftime('%Y-%m'),u['settings']['anchor'],json.dumps(a),json.dumps(errors),iso(self.now())))
                id=cur.lastrowid
            else:
                sc=self.entity(c,'schedules',d['id'],u); require(sc['version']==d['version'],'Escala alterada. Recarregue antes de salvar.',409)
                require(sc['status']=='draft','Versão publicada é imutável. Crie uma revisão.',409)
                a=d.get('assignments',json.loads(sc['assignments'])); require(isinstance(a,list) and len(a)<=1500,'Alocações inválidas.')
                errors=validate_schedule(self,c,u,a,True)
                if action=='publish':
                    require(u['settings']['anchor_confirmed'],'Confirme mês/ano e data-âncora nas configurações.')
                    require(not errors,'Escala contém conflitos e não pode ser publicada.',409,{'errors':errors})
                require(action in ('save','publish'),'Ação inválida.')
                c.execute('UPDATE schedules SET assignments=?,errors=?,version=version+1,status=? WHERE id=?',(json.dumps(a),json.dumps(errors),'published' if action=='publish' else 'draft',sc['id'])); id=sc['id']
            self.audit(c,user,u,'schedule_'+action,id,{'errors':errors}); return {'id':id,'errors':errors,'message':'Escala publicada.' if action=='publish' else 'Rascunho salvo. Confira a validação.'}
    def save_work(self,user,unit,d):
        self.role(user,'admin')
        with self.db.transaction() as c:
            u=self.scope(c,user,unit); p=self.entity(c,'people',d['person'],u); require(p['kind'] in ('internal','intern'),'Vínculo inválido.')
            require(d.get('valid_from') and d.get('valid_to') and d['valid_from']<=d['valid_to'],'Informe vigência válida.')
            require(isinstance(d.get('contract_minutes'),int) and 60<=d['contract_minutes']<=3600,'Carga contratual inválida.')
            require(not c.execute("SELECT 1 FROM schedules WHERE org=? AND unit=? AND status='published'",(u['org'],u['id'])).fetchone(),'Revisão de jornadas após publicação exige fluxo de impacto ainda pendente.',409)
            require(isinstance(d['days'],list),'Informe jornadas.')
            for w in d['days']:
                require(w['weekday'] in range(7) and minutes(w['start'])<minutes(w['end']),'Jornada inválida.')
                for r in rows(c,"SELECT * FROM reservations WHERE org=? AND unit=? AND person=? AND category='internal' AND status='confirmed' AND start>?",(u['org'],u['id'],p['id'],iso(self.now()))):
                    start=instant(r['start']).astimezone(ZoneInfo(u['settings']['timezone'])); end=instant(r['end']).astimezone(ZoneInfo(u['settings']['timezone']))
                    if start.weekday()==w['weekday'] and d['valid_from']<=start.date().isoformat()<=d['valid_to']:
                        require(not overlap(start,end,local_start(start.date().isoformat(),w['start'],u['settings']),local_start(start.date().isoformat(),w['end'],u['settings'])),'Jornada conflita com reserva particular.',409)
            # Preserve earlier intervals, reject overlapping future versions.
            c.execute('UPDATE work SET valid_to=? WHERE org=? AND unit=? AND person=? AND valid_from<? AND valid_to>=?',((date.fromisoformat(d['valid_from'])-timedelta(days=1)).isoformat(),u['org'],u['id'],p['id'],d['valid_from'],d['valid_from']))
            require(not c.execute('SELECT 1 FROM work WHERE unit=? AND person=? AND valid_from>=?',(u['id'],p['id'],d['valid_from'])).fetchone(),'Já existe jornada com vigência nesse período.',409)
            for w in d['days']: c.execute('INSERT INTO work(org,unit,person,weekday,start,end,valid_from,valid_to,contract_minutes) VALUES(?,?,?,?,?,?,?,?,?)',(u['org'],u['id'],p['id'],w['weekday'],w['start'],w['end'],d['valid_from'],d['valid_to'],d['contract_minutes']))
            self.audit(c,user,u,'work_version',p['id'],d); return {'message':'Jornada versionada salva.'}
    def resolve_block(self,user,unit,d):
        """Resolve each affected student, move atomically, split around kept bookings."""
        self.role(user,'admin','reception')
        with self.db.transaction() as c:
            u=self.scope(c,user,unit); start,end=instant(d['start']),instant(d['end']); reason=str(d.get('reason','')).strip(); require(reason and start<end,'Informe motivo e intervalo.')
            room=d.get('room'); person=d.get('person'); require(bool(room)!=bool(person),'Escolha sala OU profissional.')
            self.entity(c,'rooms' if room else 'people',room or person,u)
            affected=[r for r in rows(c,"SELECT * FROM reservations WHERE org=? AND unit=? AND status IN ('confirmed','awaiting_payment','no_show') AND start<? AND end>?",(u['org'],u['id'],iso(end),iso(start))) if (room and r['room']==room) or (person and person in (r['person'],r['tutor']))]
            decisions=d.get('decisions',{}); retained=[]
            require(affected,'Nenhum atendimento afetado. Use o bloqueio simples.')
            for r in affected:
                dec=decisions.get(str(r['id'])); require(dec and dec.get('action') in ('keep','move'),'Resolva cada atendimento: manter ou realocar.',409,{'affected':[x['id'] for x in affected]})
                if dec['action']=='keep':
                    retained.append((instant(r['start']),instant(r['end'])))
                    self.audit(c,user,u,'incident_keep',r['id'],{'reason':reason})
                else:
                    require(r['category']=='student' and r['status']=='confirmed' and r['presence']=='pendente','Realocação exclusiva exige avaliação ativa de aluno, sem falta anterior.')
                    require(dec.get('agreed') is True,'Registre ciência do aluno antes da realocação.')
                    data={'category':'student','student':r['student'],'person':dec['person'],'room':dec['room'],'start':dec['start']}
                    a,b,p,student,tutor,snap,s=self.validate_booking(c,user,u,data,r['id'],True,json.loads(r['snapshot']))
                    require(not overlap(a,b,start,end) or ((room and dec['room']!=room) or (person and dec['person']!=person)),'Destino ainda afetado pelo bloqueio.')
                    c.execute('INSERT OR IGNORE INTO benefits VALUES(?,?,?,?,?)',(u['org'],u['id'],student['cpf'],a.strftime('%Y-%m'),r['id']))
                    c.execute('UPDATE reservations SET start=?,end=?,room=?,person=?,tutor=?,relocated=1 WHERE id=?',(iso(a),iso(b),dec['room'],p['id'],tutor['id'] if tutor else None,r['id']))
                    self.audit(c,user,u,'incident_relocation',r['id'],{'before':{'start':r['start'],'room':r['room'],'person':r['person']},'after':data,'reason':reason})
            segments=[(start,end)]
            for a,b in retained:
                next_segments=[]
                for x,y in segments:
                    if overlap(x,y,a,b):
                        if x<a: next_segments.append((x,min(y,a)))
                        if b<y: next_segments.append((max(x,b),y))
                    else: next_segments.append((x,y))
                segments=next_segments
            for a,b in segments:
                c.execute('INSERT INTO blocks(org,unit,room,person,start,end,reason,operator,origin) VALUES(?,?,?,?,?,?,?,?,?)',(u['org'],u['id'],room,person,iso(a),iso(b),reason,user['id'],'operational'))
            self.audit(c,user,u,'incident_resolved','block',{'reason':reason,'decisions':decisions,'segments':len(segments)})
            return {'message':'Imprevisto resolvido; avaliações mantidas excluídas do bloqueio e realocações registradas.'}
    def swap_action(self,user,unit,action,d):
        from .scheduling import validate_schedule
        with self.db.transaction() as c:
            u=self.scope(c,user,unit)
            if action=='request':
                self.role(user,'teacher','intern'); sc=self.entity(c,'schedules',d['schedule'],u)
                require(sc['status']=='published','Selecione escala publicada.'); a=json.loads(sc['assignments']); idx=int(d['assignment']); require(0<=idx<len(a),'Plantão inválido.')
                require(a[idx]['person']==user['person'] and not a[idx].get('off') and not a[idx].get('adjustment'),'Escolha um plantão seu.')
                target=self.entity(c,'people',d['target'],u); source=self.entity(c,'people',user['person'],u)
                require(target['id']!=source['id'] and target['kind']==source['kind'] and target['active'],'Colega não é elegível para a função.')
                reason=str(d.get('reason','')).strip(); require(reason,'Informe motivo.')
                cur=c.execute("INSERT INTO swaps(org,unit,schedule,version,source,target,assignment,reason,status) VALUES(?,?,?,?,?,?,?,?,'requested')",(u['org'],u['id'],sc['id'],sc['version'],source['id'],target['id'],idx,reason)); id=cur.lastrowid
            else:
                sw=self.entity(c,'swaps',d['id'],u); id=sw['id']
                if action=='accept':
                    require(user.get('person')==sw['target'] and sw['status']=='requested','Apenas o colega destinatário pode aceitar.',403)
                    c.execute("UPDATE swaps SET status='accepted' WHERE id=?",(id,))
                elif action=='approve':
                    self.role(user,'admin'); require(sw['status']=='accepted','Colega ainda não aceitou.')
                    sc=self.entity(c,'schedules',sw['schedule'],u)
                    latest=c.execute("SELECT MAX(id) FROM schedules WHERE org=? AND unit=? AND status='published'",(u['org'],u['id'])).fetchone()[0]
                    require(latest==sc['id'] and sc['version']==sw['version'],'Escala mudou. Solicite nova validação e aceite.',409)
                    a=json.loads(sc['assignments']); a[sw['assignment']]['person']=sw['target']
                    # Discard derived Friday adjustments; recompute for all Saturday openers.
                    a=[x for x in a if not x.get('adjustment')]
                    for x in list(a):
                        if not x.get('off') and date.fromisoformat(x['date']).weekday()==5 and x['start']=='08:00':
                            friday=date.fromisoformat(x['date'])-timedelta(days=1); work=self.work_intervals(c,u,x['person'],friday,False)
                            if work and max(b.hour*60+b.minute for _,b in work)>1260:
                                duration=sum(int((b-a).total_seconds()/60) for a,b in work)
                                a.append({'date':friday.isoformat(),'person':x['person'],'start':'15:00','end':clock(900+duration),'slot':'Ajuste de sexta','adjustment':True})
                    errors=validate_schedule(self,c,u,a,True); require(not errors,'Permuta viola regras da escala.',409,{'errors':errors})
                    c.execute("INSERT INTO schedules(org,unit,version,status,month,anchor,assignments,errors,created) VALUES(?,?,?,'published',?,?,?,'[]',?)",(u['org'],u['id'],sc['version']+1,sc['month'],sc['anchor'],json.dumps(a),iso(self.now())))
                    c.execute("UPDATE swaps SET status='approved' WHERE id=?",(id,))
                else: raise RuleError('Ação inválida.')
            self.audit(c,user,u,'swap_'+action,id,d)
            return {'id':id,'message':'Permuta aprovada. Confira os novos dias e horários. O tratamento do ponto deve seguir a orientação validada da gestão/RH no Myaghora.' if action=='approve' else 'Permuta registrada.'}
    def availability(self,user,unit,d):
        with self.db.transaction() as c:
            u=self.scope(c,user,unit); self.jobs(c,u); s=self.settings_for(c,u,d['date']); category=d.get('category'); require(category in ('student','internal','external'),'Categoria inválida.')
            day=date.fromisoformat(d['date']); hours=opening(day,s); result=[]
            if not hours:return {'slots':[],'reason':'Unidade fechada.'}
            starts=slots(s) if category=='student' else [clock(m) for m in range(minutes(hours[0]),minutes(hours[1]),10)]
            for start in starts:
                data={**d,'accepted':True,'accepted_terms':{'duration':s['external_duration'],'price':s['external_price'],'retention':s['retention']},'start':iso(local_start(d['date'],start,s))}
                try:
                    self.validate_booking(c,user,u,data); result.append({'time':start,'available':True})
                except RuleError as e: result.append({'time':start,'available':False,'reason':str(e)})
            return {'slots':result,'duration':s[category+'_duration'],'price':s['external_price'] if category=='external' else 0}
    def create_user(self,user,unit,d):
        self.role(user,'admin')
        with self.db.transaction() as c:
            u=self.scope(c,user,unit); role=d.get('role'); require(role in ('manager','reception','teacher','intern'),'Perfil inválido.')
            login=str(d.get('login','')).strip().lower(); require(re.fullmatch(r'[a-z0-9._-]{3,40}',login),'Usuário: 3 a 40 caracteres simples.')
            password=str(d.get('password','')); require(len(password)>=10,'Senha inicial deve ter ao menos 10 caracteres.')
            person=None
            if role in ('teacher','intern'):
                p=self.entity(c,'people',d.get('person',0),u); require(p['active'] and p['kind']==('intern' if role=='intern' else 'internal'),'Vínculo incompatível com o perfil.')
                if role=='intern':
                    t=self.entity(c,'people',p['tutor'],u);require(t['active'] and t['kind']=='internal' and t['profession']=='pe' and p['cpf'],'Tutor/CPF inválido.')
                person=p['id']
            cur=c.execute('INSERT INTO users(org,unit,person,login,role,password) VALUES(?,?,?,?,?,?)',(u['org'],u['id'],person,login,role,hash_password(password)))
            self.audit(c,user,u,'user_created',cur.lastrowid,{'login':login,'role':role,'person':person});return {'message':'Conta individual criada. Nenhum convite ou e-mail foi enviado.'}
    def create_room(self,user,unit,d):
        self.role(user,'admin')
        with self.db.transaction() as c:
            u=self.scope(c,user,unit);name=str(d.get('name','')).strip();require(len(name)>=3,'Informe nome da sala.')
            require(not c.execute('SELECT 1 FROM rooms WHERE unit=? AND name=?',(u['id'],name)).fetchone(),'Sala já cadastrada.',409)
            cur=c.execute('INSERT INTO rooms(org,unit,name) VALUES(?,?,?)',(u['org'],u['id'],name));self.audit(c,user,u,'room_created',cur.lastrowid,{'name':name});return {'message':'Sala cadastrada. Capacidade ainda depende de avaliadores disponíveis.'}
