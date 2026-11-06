CREATE TABLE prisma_agenda.runtime_installation(
 id TEXT PRIMARY KEY CHECK(id='primary'),
 org INTEGER NOT NULL DEFAULT 1 REFERENCES prisma_agenda.organizations(id),
 rate_salt TEXT NOT NULL CHECK(length(rate_salt)=64),
 setup_hash TEXT,
 setup_expires TIMESTAMPTZ
);
CREATE TABLE prisma_agenda.login_limits(bucket TEXT PRIMARY KEY,attempts INTEGER NOT NULL,expires TIMESTAMPTZ NOT NULL);
ALTER TABLE prisma_agenda.runtime_installation ENABLE ROW LEVEL SECURITY;
ALTER TABLE prisma_agenda.login_limits ENABLE ROW LEVEL SECURITY;
CREATE POLICY backend_only ON prisma_agenda.runtime_installation TO prisma_agenda_runtime USING(true) WITH CHECK(true);
CREATE POLICY backend_only ON prisma_agenda.login_limits TO prisma_agenda_runtime USING(true) WITH CHECK(true);
GRANT SELECT,UPDATE ON prisma_agenda.runtime_installation TO prisma_agenda_runtime;
GRANT SELECT,INSERT,UPDATE,DELETE ON prisma_agenda.login_limits TO prisma_agenda_runtime;
REVOKE ALL ON prisma_agenda.runtime_installation,prisma_agenda.login_limits FROM PUBLIC,anon,authenticated;
CREATE INDEX login_limits_expiry ON prisma_agenda.login_limits(expires);

-- Invoker-only maintenance. The cron owner runs it; no browser role can call it.
CREATE FUNCTION prisma_agenda.process_due_reservations() RETURNS void
LANGUAGE plpgsql SECURITY INVOKER SET search_path=prisma_agenda,pg_catalog AS $$
DECLARE r reservations%ROWTYPE; p people%ROWTYPE; terms jsonb; at_time timestamptz; paid payments%ROWTYPE; kept integer;
BEGIN
 PERFORM pg_advisory_xact_lock(1347569997,1);
 DELETE FROM sessions WHERE expires<=now();
 DELETE FROM login_limits WHERE expires<=now();
 FOR r IN SELECT * FROM reservations WHERE status='awaiting_payment' AND expires<=now() FOR UPDATE LOOP
  UPDATE reservations SET status='expired' WHERE id=r.id;
  INSERT INTO audit(org,unit,actor,action,entity,data,created) VALUES(r.org,r.unit,0,'hold_expired',r.id::text,'{}',now());
  INSERT INTO notifications(org,unit,message,created) VALUES(r.org,r.unit,'Reserva #'||r.id||': hold_expired',now());
 END LOOP;
 FOR r IN SELECT * FROM reservations WHERE status='confirmed' AND category='student' AND presence='pendente' AND start+interval '5 minutes'<now() FOR UPDATE LOOP
  UPDATE reservations SET status='no_show',presence='faltou' WHERE id=r.id;
  INSERT INTO audit(org,unit,actor,action,entity,data,created) VALUES(r.org,r.unit,0,'student_no_show',r.id::text,'{}',now());
  INSERT INTO notifications(org,unit,message,created) VALUES(r.org,r.unit,'Reserva #'||r.id||': student_no_show',now());
 END LOOP;
 FOR r IN SELECT * FROM reservations WHERE status='confirmed' AND category<>'student' AND used=0 AND (snapshot::jsonb->>'professional_no_show_confirmed')::boolean IS TRUE AND (snapshot::jsonb->>'use_deadline_minutes') IS NOT NULL AND "end"+((snapshot::jsonb->>'use_deadline_minutes')::integer*interval '1 minute')<now() FOR UPDATE LOOP
  terms:=r.snapshot::jsonb;
  at_time:=r."end"+((terms->>'use_deadline_minutes')::integer*interval '1 minute');
  UPDATE reservations SET status='no_show' WHERE id=r.id;
  IF r.category='internal' THEN
   SELECT * INTO p FROM people WHERE id=r.person AND org=r.org AND unit=r.unit;
   INSERT INTO penalties(org,unit,identity,reservation,start,"end",reason)
   VALUES(r.org,r.unit,COALESCE(p.registry,CASE WHEN p.cpf IS NOT NULL THEN 'CPF:'||p.cpf ELSE 'PERSON:'||p.id END),r.id,at_time,at_time+((terms->>'penalty_hours')::integer*interval '1 hour'),'Uso não confirmado') ON CONFLICT(reservation) DO NOTHING;
  ELSE
   SELECT * INTO paid FROM payments WHERE reservation=r.id AND org=r.org AND unit=r.unit;
   IF FOUND THEN
    kept:=paid.amount*(terms->>'retention')::integer/100;
    INSERT INTO refunds(org,unit,reservation,amount,retained,created) VALUES(r.org,r.unit,r.id,paid.amount-kept,kept,now()) ON CONFLICT(reservation) DO NOTHING;
    UPDATE reservations SET payment='refund_pending' WHERE id=r.id;
   END IF;
  END IF;
  INSERT INTO audit(org,unit,actor,action,entity,data,created) VALUES(r.org,r.unit,0,'professional_no_show',r.id::text,'{}',now());
  INSERT INTO notifications(org,unit,message,created) VALUES(r.org,r.unit,'Reserva #'||r.id||': professional_no_show',now());
 END LOOP;
END $$;
REVOKE ALL ON FUNCTION prisma_agenda.process_due_reservations() FROM PUBLIC,anon,authenticated,prisma_agenda_runtime;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM pg_available_extensions WHERE name='pg_cron') THEN
  CREATE EXTENSION IF NOT EXISTS pg_cron;
  PERFORM cron.schedule('prisma-agenda-due-reservations','* * * * *','SELECT prisma_agenda.process_due_reservations();');
 END IF;
END $$;
