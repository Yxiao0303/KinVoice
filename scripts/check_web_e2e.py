"""Real Chromium + real local API/Engine; offline provider and synthetic users only."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-python',default=sys.executable)
    args=parser.parse_args()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    checks=[]
    with tempfile.TemporaryDirectory(prefix='kinvoice-browser-') as tmp:
        with open(Path(tmp)/'server.log','w+') as log:
            process=subprocess.Popen([args.server_python,str(ROOT/'scripts/offline_web_demo.py'),'--port',str(port)],cwd=ROOT,stdout=log,stderr=log)
            try:
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                for _ in range(100):
                    try:
                        if opener.open(base+'/ping',timeout=1).status==200: break
                    except Exception: time.sleep(.1)
                else: raise AssertionError('local mock server did not start')
                with sync_playwright() as p:
                    executable=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium')
                    browser=p.chromium.launch(headless=True,**({'executable_path':executable} if executable else {}))
                    context=browser.new_context(viewport={'width':1440,'height':1000})
                    external=[]
                    def network(route):
                        if route.request.url.startswith(base+'/'): route.continue_()
                        else: external.append(route.request.url); route.abort()
                    context.route('**/*',network)
                    page=context.new_page(); errors=[]; requests=[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.on('request',lambda r:requests.append(r.post_data_json) if r.url.endswith(('/support/stream','/support/student')) else None)
                    page.goto(base)
                    expect(page.locator('#home-mode')).to_contain_text('离线 mock')
                    def register(name):
                        page.locator('[data-enter]').first.click()
                        if '创建账号' in page.locator('#auth-toggle').inner_text(): page.locator('#auth-toggle').click()
                        page.locator('#username').fill(name); page.locator('#password').fill('synthetic-password-only')
                        page.locator('#auth-submit').click()
                        expect(page.locator('#chat-view')).to_be_visible()
                        page.locator('#eligible').check()
                        if not page.locator('#inspector').is_visible(): page.locator('#toggle-inspector').click()
                    def send(text):
                        n=page.locator('.message.assistant').count()
                        page.locator('#message').fill(text); page.locator('#send').click()
                        expect(page.locator('.message.assistant')).to_have_count(n+1)
                        expect(page.locator('#send')).to_be_enabled()
                    register('synthetic_alice')
                    send('虚构场景：父母希望我回家，我很难过。')
                    expect(page.locator('.message-label').last).to_contain_text('离线 mock')
                    page.locator('#state-review summary').click()
                    emotion=page.locator('#review-controls > div').filter(has_text='情绪理解')
                    emotion.get_by_role('button',name='确认原判断').click()
                    emotion.get_by_role('button',name='确认原判断').click()
                    send('继续这个虚构场景。')
                    assert len(requests[-1]['reviews'])==1 and requests[-1]['reviews'][0]['revision']==1
                    emotion=page.locator('#review-controls > div').filter(has_text='情绪理解')
                    emotion.locator('select').select_option('angry'); emotion.get_by_role('button',name='采用更正').click()
                    send('继续这个虚构场景。')
                    expect(page.locator('#review-controls > div').filter(has_text='情绪理解').locator('select')).to_have_value('angry')
                    page.locator('#review-controls > div').filter(has_text='情绪理解').get_by_role('button',name='撤销此判断').click()
                    send('继续这个虚构场景。')
                    expect(page.locator('#review-controls > div').filter(has_text='情绪理解').locator('select')).to_have_value('unknown')
                    assert requests[-1]['reviews'][0]['revision']==3
                    checks.append('UI confirm/correct/revoke propagation and duplicate-review idempotency')
                    page.locator('#new-chat').click()
                    send('虚构场景 [MOCK:reject]')
                    expect(page.locator('.message-content').last).to_contain_text('未能生成通过检查')
                    assert '你必须马上原谅' not in page.locator('#messages').inner_text()
                    checks.append('real Engine rejection/fallback; rejected draft never displayed')
                    page.locator('#new-chat').click()
                    send('虚构场景 [MOCK:verdict]')
                    expect(page.locator('.message-content').last).to_contain_text('未能生成通过检查')
                    checks.append('model-verdict mock rejection uses real fallback')
                    page.locator('#new-chat').click()
                    page.route('**/support/stream', lambda route:route.fulfill(status=200, content_type='application/x-ndjson', body='{\"type\":\"start\",\"protocol\":\"ccare-stream-v1\",\"sequence\":1}\n'), times=1)
                    page.locator('#message').fill('虚构断流场景'); page.locator('#send').click()
                    expect(page.locator('#chat-status')).to_contain_text('连接提前结束')
                    expect(page.locator('.message.assistant')).to_have_count(0)
                    checks.append('truncated stream rejects incomplete reply (browser network fixture)')
                    page.locator('#new-chat').click()
                    before=len(requests)
                    page.locator('#message').fill('虚构慢速 [MOCK:slow]')
                    page.evaluate("() => {document.querySelector('#chat-form').requestSubmit(); document.querySelector('#chat-form').requestSubmit();}")
                    expect(page.locator('#pause')).to_be_enabled()
                    expect(page.locator('#trace-stages')).to_contain_text('正在处理')
                    assert len(requests)==before+1
                    page.locator('#pause').click()
                    page.wait_for_timeout(2300) # deliberately longer than the fixture stage delay
                    expect(page.locator('.message.assistant')).to_have_count(0)
                    page.locator('#new-chat').click(); send('新的虚构会话。')
                    assert requests[-1]['history']==[] and requests[-1]['reviews']==[]
                    checks.append('duplicate submit blocked; real stream pause; new chat has no old context')
                    # Browser-side fault injection holds a completed old response even
                    # though AbortController fires. The API/Engine response is real.
                    page.evaluate("""() => { const original=window.fetch; window.__holdNext=true;
                      window.fetch=async (...args) => {const response=await original(...args);
                        if(String(args[0]).endsWith('/support/stream') && window.__holdNext) {
                          window.__holdNext=false; const body=await response.arrayBuffer();
                          window.__held=true; await new Promise(resolve=>window.__releaseOld=resolve);
                          return new Response(body,{status:response.status,headers:response.headers});
                        } return response; }; }""")
                    page.locator('#message').fill('旧响应虚构标记'); page.locator('#send').click()
                    for _ in range(100):
                        if page.evaluate('() => window.__held === true'): break
                        page.wait_for_timeout(50)
                    else: raise AssertionError('old response not held')
                    page.locator('#new-chat').click(); send('新响应虚构标记')
                    page.evaluate('window.__releaseOld()'); page.wait_for_timeout(100)
                    expect(page.locator('.message.assistant')).to_have_count(1)
                    assert '旧响应虚构标记' not in page.locator('#messages').inner_text()
                    checks.append('delayed old response cannot overwrite new chat (browser fault injection)')
                    page.evaluate('() => {window.__held=false; window.__holdNext=true;}')
                    page.locator('#message').fill('旧账号待返回虚构标记'); page.locator('#send').click()
                    for _ in range(100):
                        if page.evaluate('() => window.__held === true'): break
                        page.wait_for_timeout(50)
                    else: raise AssertionError('old account response not held')
                    page.locator('#logout').click(); expect(page.locator('#home-view')).to_be_visible()
                    register('synthetic_bob')
                    expect(page.locator('#messages')).to_be_empty()
                    send('另一账号的虚构消息')
                    assert requests[-1]['history']==[] and requests[-1]['reviews']==[]
                    page.evaluate('window.__releaseOld()'); page.wait_for_timeout(100)
                    expect(page.locator('.message.assistant')).to_have_count(1)
                    assert '旧账号待返回虚构标记' not in page.locator('#messages').inner_text()
                    assert '新响应虚构标记' not in page.locator('#messages').inner_text()
                    assert page.evaluate('localStorage.length + sessionStorage.length')==0
                    checks.append('logout/account switch clears messages, reviews and browser storage')
                    # Real student endpoint: deterministic rules, no provider calls.
                    page.locator('#new-chat').click()
                    page.locator('#student-mode').check()
                    page.locator('#message').fill('这次考试没考好，妈妈说我不努力。')
                    page.locator('#send').click()
                    expect(page.locator('#chat-status')).to_contain_text('单独确认')
                    page.locator('#student-adult').check()
                    send('这次考试没考好，妈妈说我不努力。')
                    expect(page.locator('#student-card')).to_be_visible()
                    expect(page.locator('#student-event-summary')).to_contain_text('学业与家庭')
                    expect(page.locator('#student-event-summary')).to_contain_text('妈妈')
                    if not page.locator('#review-controls').is_visible():page.locator('#state-review summary').click()
                    subject=page.locator('#review-controls > div').filter(has_text='事件主体')
                    subject.locator('select').select_option('father')
                    subject.get_by_role('button',name='采用更正').click()
                    send('继续这件事。')
                    expect(page.locator('#student-event-summary')).to_contain_text('爸爸')
                    event=page.locator('#review-controls > div').filter(has_text='这条事件记录')
                    event.get_by_role('button',name='撤销此判断').click()
                    send('继续。')
                    expect(page.locator('#student-event-summary')).not_to_contain_text('爸爸')
                    page.locator('#student-support').select_option('draft')
                    send('帮我写一句明天再谈考试的话。')
                    expect(page.locator('.message-content').last).to_contain_text('明天再谈')
                    expect(page.locator('#trace-calls')).to_contain_text('0')
                    page.locator('#new-chat').click()
                    expect(page.locator('#student-card')).to_be_hidden()
                    send('我还没想好。')
                    assert requests[-1]['history']==[] and requests[-1]['reviews']==[]
                    page.locator('#student-mode').uncheck()
                    expect(page.locator('#student-card')).to_be_hidden()
                    expect(page.locator('#messages')).to_be_empty()
                    checks.append('student offline UI admission, evidence card, subject correction, event withdrawal, drafting and clear/isolation')
                    isolated=browser.new_context(); isolated.route('**/*',network); other=isolated.new_page(); other.goto(base+'/#chat')
                    expect(other.locator('#auth-dialog')).to_be_visible()
                    expect(other.locator('#chat-view')).to_be_hidden()
                    checks.append('new browser context cannot inherit authentication')
                    assert not errors,errors
                    assert not external,external
                    print(json.dumps({'browser':'Chromium','mode':'offline_mock','passed':checks,'page_errors':errors,'external_requests':external,'real_model_calls':0},ensure_ascii=False))
                    browser.close()
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait()

if __name__=='__main__': main()
