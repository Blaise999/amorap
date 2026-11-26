"""AMORAP live chat: actual guest/admin API, private tokens, replies and contact edits."""
import sys,tempfile,threading,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from qa_admin import server,Client,TestDB

with tempfile.TemporaryDirectory() as tmp:
 db=TestDB(str(Path(tmp)/'chat.sqlite'));db.setup();server.db=db.connect
 class Quiet(server.Handler):
  def log_message(self,*args):pass
 web=server.ThreadingHTTPServer(('127.0.0.1',0),Quiet)
 threading.Thread(target=web.serve_forever,daemon=True).start()
 try:
  guest=Client(web.server_port);stranger=Client(web.server_port);admin=Client(web.server_port)
  admin.login()
  assert admin.get()['chats']==[]
  stranger.send('GET','/api/admin/chats',expected=401)
  guest.send('POST','/api/chat/start',{'name':'','message':''},expected=400)
  first=guest.send('POST','/api/chat/start',{'name':'QA Visitor','email':'guest@example.test','message':'Can I bring a dog?'},201)
  token=first['token'];cid=first['chat']['id']
  assert len(token)==43 and first['chat']['messages'][0]['text']=='Can I bring a dog?'
  stranger.send('POST','/api/chat/poll',{'id':cid},expected=404)
  stranger.send('POST','/api/chat/send',{'id':cid,'token':None,'message':'Intruder'},expected=404)
  stranger.send('POST','/api/chat/poll',{'id':cid,'token':'wrong'},expected=404)
  stranger.send('POST','/api/chat/send',{'id':cid,'token':'wrong','message':'Intruder'},expected=404)
  stranger.send('POST','/api/chat/poll',{'id':cid+1,'token':token},expected=404)
  assert guest.send('POST','/api/chat/poll',{'id':cid,'token':token})['chat']['status']=='open'
  inbox=admin.get('chats')['chats']
  assert len(inbox)==1 and inbox[0]['guestName']=='QA Visitor' and inbox[0]['email']=='guest@example.test'
  assert 'token' not in json.dumps(inbox).lower()
  full=admin.get()
  assert full['messages']==[] and len(full['chats'])==1

  reply=admin.send('POST','/api/admin/chat/reply',{'id':cid,'message':'Yes, for selected pet-friendly villas.'})['chat']
  assert reply['messages'][-1]['role']=='admin'
  assert guest.send('POST','/api/chat/poll',{'id':cid,'token':token})['chat']['messages'][-1]['text'].startswith('Yes')
  sent=guest.send('POST','/api/chat/send',{'id':cid,'token':token,'message':'Thank you!'})
  assert sent['chat']['messages'][-1]['role']=='guest'
  admin.send('POST','/api/admin/chat/status',{'id':cid,'status':'closed'})
  guest.send('POST','/api/chat/send',{'id':cid,'token':token,'message':'Are you there?'},expected=409)
  admin.send('POST','/api/admin/chat/reply',{'id':cid,'message':'Closed now'},expected=409)
  admin.send('POST','/api/admin/chat/status',{'id':cid,'status':'open'})
  assert guest.send('POST','/api/chat/send',{'id':cid,'token':token,'message':'Another question'})['chat']['status']=='open'
  stranger.send('POST','/api/admin/chat/reply',{'id':cid,'message':'unauthorized'},expected=401)
  assert not guest.send('POST','/api/chat/poll',{'id':cid,'token':token})['chat'].get('tokenHash')

  guest.send('POST','/api/contact',{'name':'QA Contact','email':'qa@example.test','message':'Contact-form message'},201)
  assert len(admin.get()['messages'])==1
  assert admin.get()['messages'][0]['message']=='Contact-form message'
  assert len(admin.get()['chats'])==1

  dashboard=admin.get()
  assert dashboard['support']['resortAddress'].startswith('Brgy.')
  saved=admin.save('support',{'phone':'+63 (912) 345-6789','dialPhone':'+639123456789',
      'email':'reception@example.test','resortAddress':'Updated resort address',
      'officeAddress':'Updated head office','hours':'24/7','greeting':'Chat with us'},
      dashboard['revisions']['support'])
  assert saved['value']['officeAddress']=='Updated head office'
  assert guest.send('GET','/api/catalog')['support']['resortAddress']=='Updated resort address'
  support=admin.get();admin.save('support',{'phone':'','dialPhone':'','email':'',
      'resortAddress':'','officeAddress':'','hours':'','greeting':''},
      support['revisions']['support'])
  after=guest.send('GET','/api/catalog')['support']
  assert after['phone']=='' and after['dialPhone']=='' and after['officeAddress']=='' and after['resortAddress']==''
  print('PASS private chat tokens, guest/admin replies, polling and open/close; contacts kept separate')
  print('PASS admin editable and removable phone, tap-to-call, email, resort and head-office address')
 finally:
  web.shutdown();web.server_close()
