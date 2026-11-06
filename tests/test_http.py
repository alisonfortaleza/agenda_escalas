"""HTTP security contracts on an ephemeral loopback port; no browser preview."""
import unittest,tempfile,threading,json,http.client
from app.db import Database
from app.service import Service
from app.server import AppServer

class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();db=Database(cls.tmp.name+'/api.sqlite');db.migrate();db.seed()
        cls.server=AppServer(('127.0.0.1',0),Service(db),True);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.port=cls.server.server_address[1]
    @classmethod
    def tearDownClass(cls): cls.server.shutdown();cls.server.server_close();cls.tmp.cleanup()
    def request(self,path,body=None,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.port);h={'Host':f'127.0.0.1:{self.port}'}
        if body is not None:h.update({'Content-Type':'application/json','Origin':f'http://127.0.0.1:{self.port}'})
        h.update(headers or {});c.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,h);r=c.getresponse();data=r.read();status=r.status;hs=dict(r.getheaders());c.close();return status,hs,data
    def login(self):
        status,h,b=self.request('/api/login',{'org':1,'login':'recepcao','password':'Demo@2026!'});self.assertEqual(status,200);return {'Cookie':h['Set-Cookie'].split(';')[0],'X-CSRF-Token':json.loads(b)['csrf']}
    def test_no_auth_no_data(self): self.assertEqual(self.request('/api/state')[0],401)
    def test_host_and_origin_protection(self):
        self.assertEqual(self.request('/api/health',headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.request('/api/login',{'login':'admin','bootstrap':True},headers={'Origin':'http://evil.example'})[0],403)
    def test_cookie_http_only_and_csrf(self):
        h=self.login();h.pop('X-CSRF-Token');self.assertEqual(self.request('/api/block',{'reason':'Test'},h)[0],403)
    def test_reception_cannot_fetch_schedule_export_or_other_unit(self):
        h=self.login()
        for url in ['/api/schedules','/api/export','/api/state?unit=2']:
            self.assertEqual(self.request(url,headers=h)[0],403)
    def test_frontend_security_headers_and_static(self):
        status,h,b=self.request('/');self.assertEqual(status,200);self.assertIn(b'Prisma',b);self.assertIn("frame-ancestors 'none'",h['Content-Security-Policy']);self.assertEqual(h['Cache-Control'],'no-store')
    def test_logout_invalidates_session(self):
        h=self.login();self.assertEqual(self.request('/api/logout',{},h)[0],200);self.assertEqual(self.request('/api/state',headers=h)[0],401)
