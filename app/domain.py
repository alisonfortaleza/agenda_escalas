"""Pure rules; civil calendar is interpreted in the unit's timezone."""
from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo
import re

class RuleError(Exception):
    def __init__(self, message, status=422, details=None):
        super().__init__(message); self.status=status; self.details=details

def require(ok, message, status=422, details=None):
    if not ok: raise RuleError(message,status,details)

def normalize_name(value):
    value=' '.join(str(value).split())
    require(len(value.split())>=2 and all(re.fullmatch(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*",p,re.UNICODE) for p in value.split()),'Informe nome e sobrenome completos.')
    return value

def cpf(value):
    n=re.sub(r'\D','',str(value))
    require(len(n)==11 and len(set(n))>1,'CPF inválido.')
    for size in (9,10):
        digit=(sum(int(n[i])*(size+1-i) for i in range(size))*10)%11%10
        require(digit==int(n[size]),'CPF inválido.')
    return n

def phone(value):
    n=re.sub(r'\D','',str(value)); require(len(n) in (10,11),'Informe telefone com DDD.'); return n

def overlap(a,b,c,d): return a<d and c<b

def minutes(t):
    try:
        h,m=map(int,t.split(':')); require(0<=h<24 and 0<=m<60,'Horário inválido.'); return h*60+m
    except (ValueError,AttributeError): raise RuleError('Horário inválido.')

def clock(n): return f'{n//60:02d}:{n%60:02d}'

def instant(value):
    try:
        d=datetime.fromisoformat(value); require(d.tzinfo is not None,'Data precisa conter fuso horário.'); return d
    except (ValueError,TypeError): raise RuleError('Data inválida.')

def iso(d): return d.astimezone(timezone.utc).isoformat(timespec='seconds')

def local_start(day,time,settings):
    try: return datetime.combine(date.fromisoformat(day),datetime.strptime(time,'%H:%M').time(),ZoneInfo(settings['timezone']))
    except (ValueError,KeyError): raise RuleError('Data ou hora inválida.')

def opening(day,s):
    ex=s['holidays'].get(day.isoformat())
    if ex is not None: return None if ex.get('closed') else ex['hours']
    return s['opening'][str(day.weekday())]

def slots(s):
    return [clock(x) for a,b in s['windows'] for x in range(minutes(a),minutes(b)-s['student_duration']+1,s['student_duration'])][:s['daily_offer']]

def capacity(s): return sum((minutes(b)-minutes(a))//s['student_duration'] for a,b in s['windows'])

def validate_settings(s):
    require(isinstance(s,dict),'Configuração inválida.')
    for key in ('external_weekdays','external_outside','internal_outside','anchor_confirmed','supervision_confirmed','intern_penalty_confirmed','professional_no_show_confirmed'):
        require(isinstance(s.get(key),bool),'Campo booleano inválido: '+key)
    require(s['penalty_hours']==48,'Perfil atual exige penalidade de 48h.')
    require(s.get('use_deadline_minutes') is None or (isinstance(s['use_deadline_minutes'],int) and 0<=s['use_deadline_minutes']<=10080),'Prazo de uso inválido.')
    try: date.fromisoformat(s['effective_from'])
    except (ValueError,KeyError,TypeError): raise RuleError('Vigência inválida.')
    for day in range(7):
        hours=s['opening'].get(str(day)); require(hours is not None and len(hours)==2 and minutes(hours[0])<minutes(hours[1]),'Funcionamento semanal inválido.')
        if day<4:
            for a,b in s['windows']: require(minutes(hours[0])<=minutes(a)<minutes(b)<=minutes(hours[1]),'Janela de aluno fora do funcionamento.')
    for day,ex in s['holidays'].items():
        date.fromisoformat(day); require(isinstance(ex,dict),'Exceção inválida.')
        if not ex.get('closed'): require(len(ex.get('hours',[]))==2 and minutes(ex['hours'][0])<minutes(ex['hours'][1]),'Horário de feriado inválido.')
    require(s['timezone'] in ('America/Recife','America/Sao_Paulo','UTC'),'Fuso não suportado.')
    for key in ('student_duration','internal_duration','external_duration'): require(s[key] in (20,30,40,50,60),'Duração deve ser 20, 30, 40, 50 ou 60 minutos.')
    for a,b in s['windows']: require(minutes(a)<minutes(b),'Janela inválida.')
    for i,(a,b) in enumerate(s['windows']):
        for c,d in s['windows'][i+1:]: require(not overlap(minutes(a),minutes(b),minutes(c),minutes(d)),'Janelas sobrepostas.')
    require(0<=s['daily_offer']<=capacity(s),f'Oferta excede a capacidade de {capacity(s)} avaliações por sala/dia.')
    require(0<=s['retention']<=100 and isinstance(s['external_price'],int) and s['external_price']>=0,'Valor ou retenção inválidos.')
    require(1<=s['hold_minutes']<=60,'Validade temporária entre 1 e 60 minutos.')
    require(s['anchor'].endswith('-01'),'Confirme o primeiro dia do mês como âncora.'); date.fromisoformat(s['anchor'])
    for cat in ('internal','external'): require(s[cat+'_sharing'] in ('shared','exclusive'),'Compartilhamento inválido.')
    return s

def cycle(day,anchor):
    n=(day-anchor).days
    return None if n<0 else {'cycle':n//84+1,'week':(n%84)//7+1}

def default_settings():
    return {'timezone':'America/Recife','student_duration':30,'internal_duration':60,'external_duration':60,'external_price':4000,'retention':50,'penalty_hours':48,'hold_minutes':10,'daily_offer':20,'windows':[['08:00','11:00'],['12:00','15:00'],['18:00','22:00']],'opening':{str(i):['05:00','23:00'] if i<5 else ['08:00','16:00'] if i==5 else ['08:00','14:00'] for i in range(7)},'holidays':{},'external_weekdays':False,'external_sharing':'shared','internal_sharing':'shared','external_outside':True,'internal_outside':True,'anchor':'2026-11-01','anchor_confirmed':False,'supervision_confirmed':False,'intern_penalty_confirmed':False,'use_deadline_minutes':None,'professional_no_show_confirmed':False,'pix_label':'DEMONSTRAÇÃO — não efetuar transferência','benefit_name':'Platinum','brand_color':'#d9f36b','contact':'Unidade fictícia / sem atendimento real','effective_from':'2026-01-01'}
