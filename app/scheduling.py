"""Schedule validation includes regular work, actual dates and adjacent weeks."""
from datetime import date,timedelta
from collections import defaultdict
from .domain import *

def load_schedule_inputs(c,u):
    args=(u['org'],u['id'])
    return {
        'people':{p['id']:dict(p) for p in c.execute('SELECT * FROM people WHERE org=? AND unit=?',args)},
        'work':[dict(w) for w in c.execute('SELECT * FROM work WHERE org=? AND unit=?',args)],
        'reservations':[dict(r) for r in c.execute("SELECT * FROM reservations WHERE org=? AND unit=? AND category='internal' AND status IN ('confirmed','awaiting_payment')",args)],
        'published':[dict(sc) for sc in c.execute("SELECT * FROM schedules WHERE org=? AND unit=? AND status='published' AND id IN (SELECT MAX(id) FROM schedules WHERE org=? AND unit=? AND status='published' GROUP BY month)",args+args)]
    }

def civil_work(ws,day,s):
    return [(local_start(day.isoformat(),w['start'],s),local_start(day.isoformat(),w['end'],s)) for w in ws if w['weekday']==day.weekday() and w['valid_from']<=day.isoformat()<=w['valid_to']]

def validate_schedule(service,c,u,assignments,require_complete=False,snapshot=None):
    data=snapshot or load_schedule_inputs(c,u)
    errors=[]; s=u['settings']; people=data['people']
    def err(message):
        if message not in errors: errors.append(message)
    days=[]
    for a in assignments:
        try:
            d=date.fromisoformat(a['date']); days.append(d); p=people.get(a['person'])
            if not p or not p['active'] or p['kind'] not in ('internal','intern'): err(f'{d}: profissional sem vínculo elegível.'); continue
            if a.get('off'): continue
            start=local_start(a['date'],a['start'],s); end=local_start(a['date'],a['end'],s)
            if not start<end: err(f'{p["name"]} {d}: intervalo inválido.')
            hours=opening(d,s)
            if not hours or minutes(a['start'])<minutes(hours[0]) or minutes(a['end'])>minutes(hours[1]): err(f'{p["name"]} {d}: fora do funcionamento.')
            expected='intern' if a.get('slot','').endswith('estágio') else 'internal'
            if not a.get('adjustment') and p['kind']!=expected: err(f'{p["name"]} {d}: função incompatível.')
            if p['kind']=='intern' and (not p['tutor'] or not p['cpf']): err(f'{p["name"]}: CPF/tutoria pendente.')
            for r in data['reservations']:
                if a['person'] in (r['person'],r['tutor']) and overlap(start,end,instant(r['start']),instant(r['end'])): err(f'{p["name"]} {d}: conflita com reserva particular #{r["id"]}.')
        except (ValueError,KeyError,TypeError): err('Alocação incompleta ou data inválida.')
    if not days: return ['Escala vazia.']
    first,last=min(days)-timedelta(days=7),max(days)+timedelta(days=7)
    anchor=date.fromisoformat(s['anchor'])
    main_dates=[date.fromisoformat(a['date']) for a in assignments if not a.get('off') and not a.get('adjustment')]
    window=anchor+timedelta(days=max(0,((min(main_dates) if main_dates else anchor)-anchor).days//84)*84)
    effective_assignments=list(assignments)
    import json
    for sc in data['published']:
        effective_assignments += [a for a in json.loads(sc['assignments']) if first<=date.fromisoformat(a['date'])<=last and not window<=date.fromisoformat(a['date'])<window+timedelta(days=84)]
    for pid,p in people.items():
        if p['kind'] not in ('internal','intern') or not p['active']: continue
        intervals=[]; worked=set(); weekly=defaultdict(int)
        ws=[w for w in data['work'] if w['person']==pid]
        if not ws:
            err(f'{p["name"]}: jornada e carga contratual ausentes.'); continue
        contract=min(w['contract_minutes'] for w in ws)
        d=first
        while d<=last:
            effective=[a for a in effective_assignments if a.get('person')==pid and a.get('date')==d.isoformat()]
            base=[] if any(a.get('off') or a.get('adjustment') for a in effective) else civil_work(ws,d,s)
            for a in effective:
                if not a.get('off'):
                    base.append((local_start(a['date'],a['start'],s),local_start(a['date'],a['end'],s)))
            for start,end in base:
                intervals.append((start,end)); worked.add(d); weekly[d-timedelta(days=d.weekday())]+=int((end-start).total_seconds()/60)
            d+=timedelta(days=1)
        intervals.sort()
        for i in range(1,len(intervals)):
            prev,cur=intervals[i-1],intervals[i]
            gap=(cur[0]-prev[1]).total_seconds()/3600
            if gap<11: err(f'{p["name"]} {cur[0].date()}: descanso inferior a 11h ou sobreposição.')
        for d in sorted(worked):
            if d.weekday()==5 and d+timedelta(days=1) in worked: err(f'{p["name"]} {d}: sábado e domingo no mesmo fim de semana.')
            if all(d+timedelta(days=i) in worked for i in range(7)): err(f'{p["name"]} {d}: sete dias consecutivos.')
            if d.isoformat() in s['holidays'] and d-timedelta(days=1) in worked: err(f'{p["name"]} {d}: trabalhou no dia anterior ao feriado.')
        for week,total in weekly.items():
            if total>contract: err(f'{p["name"]} semana {week}: carga de {total//60}h excede contrato de {contract//60}h.')
    if require_complete:
        anchor=window; end=anchor+timedelta(days=83)
        d=anchor
        while d<=end:
            for slot,start,finish,kind,count in templates(d,s):
                filled=[a for a in assignments if a.get('date')==d.isoformat() and a.get('slot')==slot and not a.get('off') and not a.get('adjustment')]
                if len(filled)!=count: err(f'{d} {slot}: cobertura {len(filled)}/{count}.')
                if any(a.get('start')!=start or a.get('end')!=finish for a in filled): err(f'{d} {slot}: horário difere do modelo.')
            d+=timedelta(days=1)
        for a in assignments:
            if not a.get('adjustment') and not a.get('off') and (not anchor<=date.fromisoformat(a['date'])<=end or not any(t[0]==a.get('slot') for t in templates(date.fromisoformat(a['date']),s))): err(f'{a.get("date")}: vaga fora do modelo/ciclo.')
        for kind in ('internal','intern'):
            eligible=[p['id'] for p in people.values() if p['active'] and p['kind']==kind]
            counts=[sum(1 for a in assignments if a['person']==pid and not a.get('off') and not a.get('adjustment') and (date.fromisoformat(a['date']).weekday()==5 or a['date'] in s['holidays'])) for pid in eligible]
            if counts and min(counts)<1: err(f'{kind}: todos precisam de ao menos um sábado/feriado no ciclo.')
            if counts and max(counts)-min(counts)>1: err(f'{kind}: distribuição sábado/feriado difere mais de um plantão.')
    return errors

def templates(d,s):
    if not opening(d,s): return []
    if d.weekday()==6: return [('Domingo','08:00','14:00','internal',1),('Domingo estágio','09:00','14:00','intern',1)]
    if d.isoformat() in s['holidays']: return [('Feriado','08:00','14:00','internal',2),('Feriado estágio','08:00','13:00','intern',1)]
    if d.weekday()==5: return [('Sábado T1','08:00','14:00','internal',1),('Sábado T2','10:00','16:00','internal',2),('Sábado estágio','08:00','13:00','intern',1)]
    return []

def generate(service,c,u,reference=None):
    s=u['settings']; root=date.fromisoformat(s['anchor']); reference=reference or root; require(reference>=root,'Período anterior à âncora.'); anchor=root+timedelta(days=((reference-root).days//84)*84); assignments=[]; counts=defaultdict(int); weekend=defaultdict(int)
    snapshot=load_schedule_inputs(c,u)
    people=[p for p in snapshot['people'].values() if p['active'] and p['kind'] in ('internal','intern')]
    d=anchor
    while d<anchor+timedelta(days=84):
        for slot,start,end,kind,count in templates(d,s):
            for _ in range(count):
                pool=sorted([p for p in people if p['kind']==kind],key=lambda p:(weekend[p['id']] if d.weekday()!=6 else counts[p['id']],counts[p['id']],p['id']))
                for p in pool:
                    a={'date':d.isoformat(),'person':p['id'],'start':start,'end':end,'slot':slot}
                    extra=[]
                    if d.isoformat() in s['holidays']:
                        extra.append({'date':(d-timedelta(days=1)).isoformat(),'person':p['id'],'off':True,'slot':'Folga pré-feriado'})
                    if d.weekday()==5 and start=='08:00':
                        friday=d-timedelta(days=1); work=civil_work([w for w in snapshot['work'] if w['person']==p['id']],friday,s)
                        if work and max(b.hour*60+b.minute for _,b in work)>21*60:
                            duration=sum(int((b-a).total_seconds()/60) for a,b in work)
                            extra.append({'date':friday.isoformat(),'person':p['id'],'start':'15:00','end':clock(900+duration),'slot':'Ajuste de sexta','adjustment':True})
                    if not validate_schedule(service,c,u,assignments+extra+[a],snapshot=snapshot):
                        assignments+=extra+[a]; counts[p['id']]+=1
                        if d.weekday()!=6: weekend[p['id']]+=1
                        break
        d+=timedelta(days=1)
    return assignments,validate_schedule(service,c,u,assignments,True,snapshot=snapshot)
