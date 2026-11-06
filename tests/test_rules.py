import unittest,tempfile,os,json,sqlite3,threading
from datetime import datetime,timedelta,date,timezone
from concurrent.futures import ThreadPoolExecutor
from app.db import Database
from app.service import Service
from app.domain import *
from app.scheduling import validate_schedule,generate,templates

class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=Database(self.tmp.name+'/test.sqlite'); self.db.migrate(); self.db.seed()
        self.time=datetime(2026,11,6,12,tzinfo=timezone.utc); self.s=Service(self.db,lambda:self.time)
        with self.db.connect() as c: self.users={r['login']:dict(r) for r in c.execute('SELECT * FROM users WHERE org=1 AND unit=1')}
        self.rec=self.users['recepcao']; self.admin=self.users['admin']; self.teacher=self.users['professor']
    def tearDown(self): self.tmp.cleanup()
    def booking(self,cat='external',day='2026-11-07',time='08:00',**kw):
        with self.db.connect() as c: settings=json.loads(c.execute('SELECT settings FROM units WHERE id=?',(kw.get('room',1) if kw.get('room') in (1,2,3) else 1,)).fetchone()[0])
        return {'accepted_terms':{'duration':settings['external_duration'],'price':settings['external_price'],'retention':settings['retention']},'category':cat,'start':day+'T'+time+':00-03:00','room':1,'person':5 if cat=='external' else 1,'student':7,'accepted':True,**kw}
    def reserve(self,data=None,user=None): return self.s.reserve(user or self.rec,1,data or self.booking())['id']
    def settings(self,**kw):
        with self.db.transaction() as c:
            row=c.execute('SELECT * FROM units WHERE id=1').fetchone(); conf=json.loads(row['settings']); conf.update(kw)
            c.execute('UPDATE units SET settings=? WHERE id=1',(json.dumps(conf),)); c.execute('UPDATE config_versions SET settings=? WHERE unit=1',(json.dumps(conf),))
    def error(self,fn,contains=None):
        with self.assertRaises(RuleError) as e: fn()
        if contains: self.assertIn(contains,str(e.exception))
        return e.exception
    def action(self,id,action,user=None,**kw): return self.s.reservation_action(user or self.rec,1,id,action,kw)
    def pay(self,id,ref='DEMO-001'): return self.action(id,'pay',amount=4000,reference=ref)

class IdentityTests(Fixture):
    def test_name_and_cpf(self):
        for n in ['Alison ','Alison','12 Santos','']:
            self.error(lambda:normalize_name(n))
        self.assertEqual(normalize_name('  José   D’Ávila  '),'José D’Ávila')
        self.assertEqual(cpf('111.444.777-35'),'11144477735')
        self.assertEqual(cpf('01234567890'),'01234567890')
        for n in ['11111111111','12345678900','123']: self.error(lambda:cpf(n))
        self.assertEqual(phone('(81) 99999-0000'),'81999990000')
    def test_bootstrap_protection(self):
        self.error(lambda:self.s.login(1,'admin','',True,False),'indisponível')
        self.assertTrue(self.s.login(1,'admin','',True,True)['temporary'])
        self.error(lambda:self.s.login(1,'admin',''),'inválido')
    def test_password_closes_bootstrap_and_sessions_persistently(self):
        a=self.s.login(1,'admin','',True,True);b=self.s.login(1,'admin','',True,True)
        self.s.set_password(self.admin,{'password':'Testing@123','confirmation':'Testing@123'})
        for token in [a['token'],b['token']]: self.error(lambda:self.s.authenticate(token),'encerrada')
        self.db.seed(); new=Service(self.db)
        self.error(lambda:new.login(1,'admin','',True,True),'indisponível')
        self.assertEqual(new.login(1,'admin','Testing@123')['user']['id'],1)
        self.assertTrue(new.login(2,'admin','',True,True)['temporary'])
    def test_unit_and_org_isolation(self):
        self.error(lambda:self.s.state(self.rec,2),'não autorizada'); self.error(lambda:self.s.state(self.admin,3),'não autorizada')
        self.assertEqual(self.s.state(self.admin,2)['people'],[])
        self.error(lambda:self.reserve(self.booking(room=2)),'não encontrado')
        self.error(lambda:self.reserve(self.booking(person=999)),'não encontrado')
    def test_direct_api_permissions(self):
        for key in ['gerente','recepcao','professor','estagiario']:
            u=self.users[key]
            self.error(lambda:self.s.schedule_action(u,1,'generate',{}),'perfil')
            self.error(lambda:self.s.update_settings(u,1,{}),'perfil')
        self.error(lambda:self.s.schedules(self.rec,1),'perfil')
        self.error(lambda:self.reserve(self.booking('internal'),self.admin),'perfil')
    def test_registry_registration(self):
        base={'kind':'external','name':'Paula Teste','phone':'81999999999','profession':'nutrition'}
        self.error(lambda:self.s.create_person(self.rec,1,base),'CRN')
        id=self.s.create_person(self.rec,1,{**base,'number':'1234','region':'6'})['id']
        with self.db.connect() as c: self.assertEqual(c.execute('SELECT registry FROM people WHERE id=?',(id,)).fetchone()[0],'CRN:6:1234')
        self.error(lambda:self.s.create_person(self.rec,1,{**base,'kind':'intern'}),'Recepção')
        self.error(lambda:self.s.create_person(self.rec,1,{**base,'login':'bypass'}),'Recepção')
        self.error(lambda:self.s.create_person(self.rec,1,{**base,'profession':'pe'}),'CREF')
    def test_intern_requires_tutor(self):
        d={'kind':'intern','name':'Aluno Estagio','phone':'81999999999','cpf':'01234567890'}
        self.error(lambda:self.s.create_person(self.admin,1,d),'não encontrado')
        self.error(lambda:self.s.create_person(self.admin,1,{**d,'tutor':5}),'Tutor')
        id=self.s.create_person(self.admin,1,{**d,'tutor':1})['id']
        with self.db.connect() as c: self.assertEqual(c.execute('SELECT tutor FROM people WHERE id=?',(id,)).fetchone()[0],1)

class BookingTests(Fixture):
    def test_concurrent_single_winner(self):
        barrier=threading.Barrier(2)
        def attempt():
            barrier.wait()
            try: return self.reserve()
            except RuleError: return None
        with ThreadPoolExecutor(2) as pool: results=list(pool.map(lambda _:attempt(),range(2)))
        self.assertEqual(sum(x is not None for x in results),1)
    def test_contiguous_halfopen(self):
        id=self.reserve(); self.pay(id)
        self.error(lambda:self.reserve(self.booking(time='08:30',person=6)),'ocupada')
        self.assertTrue(self.reserve(self.booking(time='09:00',person=6)))
    def test_nonconsecutive_blocks(self):
        self.settings(external_duration=30)
        id=self.reserve(self.booking(time='08:30'));self.pay(id)
        self.settings(external_duration=60)
        self.error(lambda:self.reserve(self.booking(time='08:00',person=6)),'ocupada')
    def test_friday_only_and_destination_week(self):
        self.assertTrue(self.reserve(self.booking('student','2026-11-09')))
        self.error(lambda:self.reserve(self.booking('student','2026-11-13',student=8)),'segunda a quinta')
        self.error(lambda:self.reserve(self.booking('student','2026-11-16',student=8)),'imediatamente')
        self.time+=timedelta(days=1)
        self.error(lambda:self.reserve(self.booking('student','2026-11-10',student=8)),'sexta')
    def test_window_edges(self):
        self.assertTrue(self.reserve(self.booking('student','2026-11-09','10:30')))
        self.assertTrue(self.reserve(self.booking('student','2026-11-10','21:30',person=3,student=8)))
        self.error(lambda:self.reserve(self.booking('student','2026-11-11','11:00',student=8)),'oferta')
    def test_monthly_identity_survives_cancel(self):
        id=self.reserve(self.booking('student','2026-11-09'));self.action(id,'cancel',reason='Aluno desistiu')
        self.error(lambda:self.reserve(self.booking('student','2026-11-10')),'CPF')
    def test_destination_month_claimed(self):
        self.time=datetime(2027,1,29,12,tzinfo=timezone.utc)
        id=self.reserve(self.booking('student','2027-02-01'))
        with self.db.connect() as c: self.assertEqual(c.execute('SELECT month FROM benefits WHERE reservation=?',(id,)).fetchone()[0],'2027-02')
    def test_external_weekday_closed_even_holiday(self):
        self.error(lambda:self.reserve(self.booking(day='2026-11-09')),'Dias úteis')
        self.settings(holidays={'2026-11-09':{'hours':['08:00','14:00']}})
        self.error(lambda:self.reserve(self.booking(day='2026-11-09')),'Dias úteis')
        self.settings(external_weekdays=True);self.assertTrue(self.reserve(self.booking(day='2026-11-09')))
    def test_internal_work_and_self(self):
        self.error(lambda:self.reserve(self.booking('internal','2026-11-09'),self.teacher),'indisponível')
        self.assertTrue(self.reserve(self.booking('internal','2026-11-09','18:00'),self.teacher))
        self.error(lambda:self.reserve(self.booking('internal','2026-11-10','18:00',person=2),self.teacher),'para si')
    def test_all_durations_and_closing(self):
        for duration in [20,30,40,50,60]:
            self.settings(external_duration=duration,external_weekdays=True)
            for day,close in [('2026-11-09',23*60),('2026-11-07',16*60),('2026-11-08',14*60)]:
                with self.subTest(duration=duration,day=day):
                    id=self.reserve(self.booking(day=day,time=clock(close-duration)));self.action(id,'cancel',reason='Fixture')
                    self.error(lambda:self.reserve(self.booking(day=day,time=clock(close-duration+10))),'funcionamento')
    def test_50_minute_boundary(self):
        self.settings(external_duration=50,external_price=5500)
        id=self.reserve(self.booking(time='09:00'));self.action(id,'pay',amount=5500,reference='FIFTY')
        self.error(lambda:self.reserve(self.booking(time='09:40',person=6)),'ocupada')
        self.assertTrue(self.reserve(self.booking(time='09:50',person=6)))
    def test_other_room_same_professional(self):
        with self.db.transaction() as c: c.execute("INSERT INTO rooms VALUES(4,1,1,'Sala 2')")
        self.reserve(); self.error(lambda:self.reserve(self.booking(room=4)),'Profissional')
    def test_exclusive_window_and_day_permission(self):
        self.settings(external_weekdays=True,external_sharing='exclusive')
        self.error(lambda:self.reserve(self.booking(day='2026-11-09')),'exclusiva')
        self.settings(external_sharing='shared');self.assertTrue(self.reserve(self.booking(day='2026-11-09')))
    def test_holiday_friday_booking_but_no_holiday_service(self):
        self.settings(holidays={'2026-11-06':{'hours':['08:00','14:00']},'2026-11-09':{'hours':['08:00','14:00']}})
        self.assertTrue(self.reserve(self.booking('student','2026-11-10')))
        self.error(lambda:self.reserve(self.booking('student','2026-11-09',student=8)),'feriados')
    def test_offer_capacity(self):
        s=default_settings();s.update(windows=[['08:00','11:00']],student_duration=40,daily_offer=4);self.assertEqual(capacity(s),4);validate_settings(s)
        s['daily_offer']=5;self.error(lambda:validate_settings(s),'capacidade de 4')
    def test_free_has_no_payment(self):
        id=self.reserve(self.booking('internal','2026-11-09','18:00'),self.teacher)
        with self.db.connect() as c:
            r=c.execute('SELECT * FROM reservations WHERE id=?',(id,)).fetchone();self.assertEqual(r['payment'],'not_applicable');self.assertEqual(c.execute('SELECT COUNT(*) FROM payments').fetchone()[0],0)
    def test_multiunit_durations(self):
        with self.db.transaction() as c:
            c.execute("INSERT INTO people(id,org,unit,name,kind,profession,registry,phone) VALUES(100,1,2,'Externo Teste','external','pe','CREF:PE:X100','81999990000')")
        u={**self.rec,'unit':2}
        id=self.s.reserve(u,2,self.booking(person=100,room=2))['id']
        with self.db.connect() as c:
            snap=json.loads(c.execute('SELECT snapshot FROM reservations WHERE id=?',(id,)).fetchone()[0]);self.assertEqual(snap['price'],8000)
        self.assertEqual(self.s.state(self.rec,1)['unit']['settings']['external_price'],4000)

class PaymentOccurrenceTests(Fixture):
    def test_acceptance_required(self): self.error(lambda:self.reserve(self.booking(accepted=False)),'aceite')
    def test_duplicate_payment_and_reference(self):
        id=self.reserve();self.pay(id)
        self.error(lambda:self.pay(id),'não aguarda')
        id2=self.reserve(self.booking(time='09:00'));self.error(lambda:self.pay(id2),'Referência')
    def test_amount_difference(self):
        id=self.reserve();self.error(lambda:self.action(id,'pay',amount=3900,reference='DIFF'),'divergente')
    def test_expired_payment_cannot_displace(self):
        id=self.reserve();self.time+=timedelta(minutes=11);self.s.job_tick()
        id2=self.reserve(self.booking(person=6));self.pay(id2,'NEW-REF')
        self.error(lambda:self.pay(id),'ocupada')
    def test_expired_can_revalidate(self):
        id=self.reserve();self.time+=timedelta(minutes=11);self.s.job_tick();self.pay(id)
        self.assertEqual(self.s.state(self.rec,1)['reservations'][0]['status'],'confirmed')
    def test_refund_uses_snapshot_and_stays_pending(self):
        id=self.reserve();self.pay(id);self.settings(external_price=8000,retention=75)
        self.action(id,'cancel',reason='Desistência')
        st=self.s.state(self.rec,1);r=st['refunds'][0];self.assertEqual((r['amount'],r['retained'],r['status']),(2000,2000,'pendente'))
        self.error(lambda:self.action(id,'cancel',reason='Repetir'),'não pode')
        self.error(lambda:self.s.refund(self.rec,1,r['id'],{'amount':2000,'reference':'RETURN'}),'efetivamente')
        self.s.refund(self.rec,1,r['id'],{'amount':2000,'reference':'RETURN','actually_refunded':True})
        self.error(lambda:self.s.refund(self.rec,1,r['id'],{'amount':2000,'reference':'RETURN','actually_refunded':True}),'já registrada')
    def test_penalty_exact_48h_and_idempotent(self):
        id=self.reserve(self.booking('internal','2026-11-09','18:00'),self.teacher)
        self.action(id,'cancel',self.teacher,reason='Desistência')
        self.error(lambda:self.reserve(self.booking('internal','2026-11-10','18:00'),self.teacher),'penalidade')
        self.time+=timedelta(hours=48)-timedelta(seconds=1)
        self.error(lambda:self.reserve(self.booking('internal','2026-11-10','18:00'),self.teacher),'penalidade')
        self.time+=timedelta(seconds=1);self.assertTrue(self.reserve(self.booking('internal','2026-11-10','18:00'),self.teacher))
        self.s.job_tick();self.s.job_tick()
        with self.db.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM penalties').fetchone()[0],1)
    def test_presence_5_minutes_boundary_and_delayed_job(self):
        id=self.reserve(self.booking('student','2026-11-09'));self.time=instant('2026-11-09T08:05:00-03:00');self.action(id,'presence')
        id2=None
        # second student's session on next day
        self.time=instant('2026-11-06T09:00:00-03:00');id2=self.reserve(self.booking('student','2026-11-10',student=8))
        self.time=instant('2026-11-10T08:05:01-03:00');self.error(lambda:self.action(id2,'presence'),'cinco minutos')
        # The job in the rejected transaction rolls back; tick durably applies it.
        self.s.job_tick();st=self.s.state(self.rec,1);self.assertEqual(next(r for r in st['reservations'] if r['id']==id2)['presence'],'faltou')
    def test_whatsapp_not_presence(self):
        id=self.reserve(self.booking('student','2026-11-09'));self.action(id,'whatsapp');self.time=instant('2026-11-09T08:06:00-03:00');self.s.job_tick()
        r=self.s.state(self.rec,1)['reservations'][0];self.assertEqual((r['whatsapp'],r['presence']),(1,'faltou'))
    def test_only_reception_justifies_and_reason_active(self):
        id=self.reserve(self.booking('student','2026-11-09'));self.time=instant('2026-11-09T08:10:00-03:00');self.s.job_tick()
        data={'reason_id':1,'detail':'Atraso real','occurred':'2026-11-09T08:07:00-03:00','actually_attended':True}
        self.error(lambda:self.action(id,'justify',self.admin,**data),'perfil')
        self.action(id,'justify',**data)
        with self.db.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM benefits').fetchone()[0],1)
    def test_inactive_reason_rejected(self):
        id=self.reserve(self.booking('student','2026-11-09'));self.time=instant('2026-11-09T08:10:00-03:00');self.s.job_tick()
        self.s.save_reason(self.admin,1,{'id':1,'title':'Inativo','active':False})
        self.error(lambda:self.action(id,'justify',reason_id=1,detail='Teste',occurred='2026-11-09T08:07:00-03:00',actually_attended=True),'inativo')
    def test_unassigned_teacher_cannot_modify(self):
        id=self.reserve(self.booking('student','2026-11-09'));self.error(lambda:self.action(id,'whatsapp',self.users['professor2']),'responsável')
    def test_usage_policy_pending_does_not_invent_penalty(self):
        id=self.reserve(self.booking('internal','2026-11-09','18:00'),self.teacher);self.time=instant('2026-11-10T12:00:00-03:00');self.s.job_tick()
        with self.db.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM penalties').fetchone()[0],0)
class IncidentConfigTests(Fixture):
    def test_personal_block_not_global(self):
        self.s.create_block(self.teacher,1,{'person':1,'start':'2026-11-09T08:00:00-03:00','end':'2026-11-09T11:00:00-03:00','reason':'Imprevisto'})
        self.error(lambda:self.reserve(self.booking('student','2026-11-09')),'bloqueado')
        self.assertTrue(self.reserve(self.booking('student','2026-11-09',person=10)))
        self.error(lambda:self.s.create_block(self.teacher,1,{'room':1,'start':'2026-11-10T08:00:00-03:00','end':'2026-11-10T11:00:00-03:00','reason':'Teste'}),'própria')
    def test_block_requires_reason_and_decision(self):
        id=self.reserve(self.booking('student','2026-11-09'))
        d={'room':1,'start':'2026-11-09T08:00:00-03:00','end':'2026-11-09T11:00:00-03:00','reason':' '}
        self.error(lambda:self.s.create_block(self.rec,1,d),'motivo')
        d['reason']='Manutenção';self.error(lambda:self.s.create_block(self.rec,1,d),'atendimentos')
        self.error(lambda:self.s.resolve_block(self.rec,1,d),'cada atendimento')
        self.s.resolve_block(self.rec,1,{**d,'decisions':{str(id):{'action':'keep'}}})
        with self.db.connect() as c:
            b=c.execute('SELECT * FROM blocks').fetchone();self.assertEqual(b['start'],iso(instant('2026-11-09T08:30:00-03:00')))
    def test_move_outside_friday_keeps_identity_and_history(self):
        id=self.reserve(self.booking('student','2026-11-09'))
        self.time=instant('2026-11-07T08:00:00-03:00')
        d={'room':1,'start':'2026-11-09T08:00:00-03:00','end':'2026-11-09T11:00:00-03:00','reason':'Manutenção','decisions':{str(id):{'action':'move','start':'2026-12-01T08:00:00-03:00','room':1,'person':1,'agreed':True}}}
        self.s.resolve_block(self.rec,1,d)
        with self.db.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM reservations').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM benefits').fetchone()[0],2)
            self.assertEqual(c.execute('SELECT relocated FROM reservations').fetchone()[0],1)
    def test_destination_conflict_rolls_back_origin_and_block(self):
        id=self.reserve(self.booking('student','2026-11-09'))
        self.reserve(self.booking('student','2026-11-10',student=8))
        d={'room':1,'start':'2026-11-09T08:00:00-03:00','end':'2026-11-09T11:00:00-03:00','reason':'Manutenção','decisions':{str(id):{'action':'move','start':'2026-11-10T08:00:00-03:00','room':1,'person':1,'agreed':True}}}
        self.error(lambda:self.s.resolve_block(self.rec,1,d),'ocupada')
        with self.db.connect() as c:
            self.assertEqual(c.execute('SELECT start FROM reservations WHERE id=?',(id,)).fetchone()[0],iso(instant('2026-11-09T08:00:00-03:00')))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM blocks').fetchone()[0],0)
    def test_config_preserves_terms_and_detects_impact(self):
        id=self.reserve();self.s.update_settings(self.admin,1,{'version':1,'settings':{'external_price':5500,'external_duration':50,'effective_from':'2026-11-06'}})
        with self.db.connect() as c: snap=json.loads(c.execute('SELECT snapshot FROM reservations').fetchone()[0]);self.assertEqual((snap['price'],snap['duration']),(4000,60))
        self.error(lambda:self.s.update_settings(self.admin,1,{'version':1,'settings':{}}),'outra sessão')
        self.error(lambda:self.s.update_settings(self.admin,1,{'version':2,'settings':{'holidays':{'2026-11-07':{'closed':True}},'effective_from':'2026-11-06'}}),'afeta reservas')
    def test_backup_restore_consistent(self):
        id=self.reserve();self.pay(id);self.action(id,'cancel',reason='Teste')
        self.s.schedule_action(self.admin,1,'generate',{})
        backup=self.tmp.name+'/backup.sqlite';self.db.backup(backup);restored=Database(backup)
        with self.db.connect() as a,restored.connect() as b:
            self.assertEqual(b.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            for table in ['reservations','payments','refunds','schedules','audit']:
                self.assertEqual([tuple(x) for x in a.execute('SELECT * FROM '+table)],[tuple(x) for x in b.execute('SELECT * FROM '+table)])

class ScheduleTests(Fixture):
    def check(self,assignments,contains):
        with self.db.connect() as c:
            u=self.s.scope(c,self.admin,1);errors=validate_schedule(self.s,c,u,assignments)
        self.assertTrue(any(contains in e for e in errors),errors)
    def test_continuous_cycle(self):
        anchor=date(2026,11,1)
        self.assertEqual(cycle(anchor+timedelta(days=83),anchor),{'cycle':1,'week':12})
        self.assertEqual(cycle(anchor+timedelta(days=84),anchor),{'cycle':2,'week':1})
        self.assertEqual(cycle(date(2027,1,1),anchor),{'cycle':1,'week':9})
        self.assertIsNone(cycle(anchor-timedelta(days=1),anchor))
    def test_weekend_and_seven_days(self):
        a=[{'date':d,'person':1,'start':'08:00','end':'14:00','slot':'Sábado T1'} for d in ['2026-11-07','2026-11-08']]
        self.check(a,'sábado e domingo');self.check(a,'sete dias')
    def test_rest_and_friday_adjustment(self):
        a=[{'date':'2026-11-07','person':3,'start':'08:00','end':'14:00','slot':'Sábado T1'}]
        self.check(a,'11h')
        a.append({'date':'2026-11-06','person':3,'start':'15:00','end':'21:00','slot':'Ajuste','adjustment':True})
        with self.db.connect() as c:
            errors=validate_schedule(self.s,c,self.s.scope(c,self.admin,1),a)
            self.assertFalse(any('11h' in e for e in errors),errors)
    def test_holiday_requires_previous_off(self):
        self.settings(holidays={'2026-11-10':{'hours':['08:00','14:00']}})
        self.check([{'date':'2026-11-10','person':1,'start':'08:00','end':'14:00','slot':'Feriado','adjustment':True}],'anterior ao feriado')
    def test_holiday_sunday_single_template(self):
        s=default_settings();s['holidays']={'2026-11-08':{'hours':['08:00','14:00']}}
        self.assertEqual(sum(t[4] for t in templates(date(2026,11,8),s)),2)
    def test_invalid_draft_cannot_publish(self):
        id=self.s.schedule_action(self.admin,1,'generate',{})['id'];self.settings(anchor_confirmed=True)
        with self.db.connect() as c: sc=dict(c.execute('SELECT * FROM schedules WHERE id=?',(id,)).fetchone())
        self.s.schedule_action(self.admin,1,'save',{'id':id,'version':sc['version'],'assignments':[]})
        self.error(lambda:self.s.schedule_action(self.admin,1,'publish',{'id':id,'version':sc['version']+1}),'conflitos')
    def test_schedule_version_conflict(self):
        id=self.s.schedule_action(self.admin,1,'generate',{})['id']
        self.error(lambda:self.s.schedule_action(self.admin,1,'save',{'id':id,'version':0,'assignments':[]}),'alterada')
    def test_intern_booking_disabled_until_policy_confirmed(self):
        self.error(lambda:self.reserve(self.booking('internal','2026-11-09','18:00',person=4),self.users['estagiario']),'pendentes')
class CompletionTests(Fixture):
    def test_valid_cycle_generation_and_publication(self):
        self.settings(anchor_confirmed=True)
        result=self.s.schedule_action(self.admin,1,'generate',{});self.assertEqual(result['errors'],[])
        self.s.schedule_action(self.admin,1,'publish',{'id':result['id'],'version':1})
        team=self.s.schedules(self.teacher,1)['schedules'];self.assertEqual(len(team),1)
        self.assertTrue(all(a['date'].startswith('2026-11') for a in team[0]['assignments']))
        self.error(lambda:self.s.schedule_action(self.admin,1,'save',{'id':result['id'],'version':2,'assignments':[]}),'imutável')
    def test_availability_returns_rule_reasons(self):
        result=self.s.availability(self.rec,1,{'date':'2026-11-09','category':'external','room':1,'person':5})
        self.assertTrue(all(not slot['available'] for slot in result['slots']));self.assertTrue(any('Dias úteis' in slot['reason'] for slot in result['slots']))
    def test_room_and_account_server_permissions(self):
        self.error(lambda:self.s.create_room(self.rec,1,{'name':'Sala 2'}),'perfil')
        self.s.create_room(self.admin,1,{'name':'Sala 2'})
        self.s.create_user(self.admin,1,{'login':'nova.recepcao','role':'reception','password':'Testing@123'})
        login=self.s.login(1,'nova.recepcao','Testing@123');self.assertEqual(login['user']['unit'],1)
        self.error(lambda:self.s.create_user(self.admin,1,{'login':'externo','role':'teacher','person':5,'password':'Testing@123'}),'incompatível')
    def test_demo_bookings_are_valid_and_seed_once(self):
        db=Database(self.tmp.name+'/demo.sqlite');db.migrate();db.seed(demo_bookings=True);db.seed(demo_bookings=True)
        with db.connect() as c:
            rs=list(c.execute('SELECT * FROM reservations ORDER BY start'));self.assertEqual(len(rs),4)
            for i,r in enumerate(rs):
                for q in rs[i+1:]: self.assertFalse(r['room']==q['room'] and overlap(r['start'],r['end'],q['start'],q['end']))
    def test_restore_clears_sessions_and_preserves_password(self):
        from app.maintenance import restore
        self.s.set_password(self.admin,{'password':'Testing@123','confirmation':'Testing@123'})
        self.s.login(1,'admin','Testing@123')
        backup=self.tmp.name+'/snapshot.sqlite';self.db.backup(backup);target=self.tmp.name+'/restored.sqlite';restore(backup,target)
        restored=Database(target)
        with restored.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
        self.assertEqual(Service(restored).login(1,'admin','Testing@123')['user']['id'],1)
    def test_job_configured_idempotent_penalty(self):
        self.settings(use_deadline_minutes=120,professional_no_show_confirmed=True)
        id=self.reserve(self.booking('internal','2026-11-09','18:00'),self.teacher)
        self.time=instant('2026-11-09T21:01:00-03:00');self.s.job_tick();self.s.job_tick()
        with self.db.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM penalties WHERE reservation=?',(id,)).fetchone()[0],1)
class RegressionTests(Fixture):
    def test_changed_terms_require_new_acceptance(self):
        data=self.booking();self.settings(external_price=5500)
        self.error(lambda:self.reserve(data),'termos mudaram')
    def test_second_cycle_has_original_anchor(self):
        result=self.s.schedule_action(self.admin,1,'generate',{'date':'2027-01-25'})
        with self.db.connect() as c:
            sc=c.execute('SELECT * FROM schedules WHERE id=?',(result['id'],)).fetchone();self.assertEqual(sc['anchor'],'2026-11-01')
            a=json.loads(sc['assignments']);actual=[x for x in a if not x.get('adjustment') and not x.get('off')]
            self.assertTrue(all(cycle(date.fromisoformat(x['date']),date(2026,11,1))['cycle']==2 for x in actual))
    def test_finance_and_personal_data_not_sent_to_teacher(self):
        st=self.s.state(self.teacher,1);self.assertNotIn('payments',st);self.assertNotIn('refunds',st)
        self.assertTrue(all('cpf' not in p and 'phone' not in p for p in st['people'] if p['kind']!='student'))
