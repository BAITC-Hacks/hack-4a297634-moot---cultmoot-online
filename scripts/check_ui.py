"""Isolated UI checks: no live OpenAI calls, no customer database access."""
import os
import sys
import tempfile
import subprocess
import time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

if '--server' in sys.argv:
    from backend import accounts
    from backend.config import settings
    accounts.DB=Path(os.environ['HV_TEST_DATABASE'])
    settings.origins=['http://127.0.0.1:8011'];settings.mode='assistant'
    import uvicorn
    uvicorn.run('backend.main:app',host='127.0.0.1',port=8011,log_level='error')
    raise SystemExit

scratch=Path(os.environ.get('HV_TEST_SCRATCH',tempfile.gettempdir()))/'halyk-voice-tests'
scratch.mkdir(parents=True,exist_ok=True)
with tempfile.TemporaryDirectory(dir=scratch) as tmp:
    env=os.environ.copy();env['HV_TEST_DATABASE']=str(Path(tmp)/'ui.sqlite3')
    process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--server'],cwd=ROOT,env=env)
    try:
        for attempt in range(100):
            try:
                if httpx.get('http://127.0.0.1:8011/health/live').status_code==200:break
            except httpx.HTTPError:time.sleep(.1)
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,channel=os.getenv('HV_BROWSER_CHANNEL','msedge'),args=['--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream'])
            page=browser.new_page(viewport={'width':1440,'height':1040})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            # Test audio requests locally; never send provider API requests in UI checks.
            page.route('**/api/audio/**',lambda route:route.fulfill(status=200,content_type='audio/pcm',body=b'\x00\x00'*72000))
            voice_routes=[]
            def voice_mock(route):
                voice_routes.append(route)
                route.on_message(lambda message:None)
                route.send('{"type":"ready"}')
            page.route_web_socket('**/api/voice?*',voice_mock)
            page.goto('http://127.0.0.1:8011/register')
            page.get_by_label('Email / Gmail').fill('ui-check@example.invalid')
            page.get_by_label('Пароль',exact=True).fill('ui-check-password-2026')
            page.get_by_role('button',name='Создать аккаунт →',exact=True).click()
            expect(page.get_by_role('heading',name='Здравствуйте! Я рядом.')).to_be_visible()
            expect(page.get_by_text('Тестовая версия · без подключения к банку',exact=False)).to_be_visible()
            # Real WebAudio playback, fake provider stream, and a fake microphone device.
            page.get_by_role('button',name='Включить микрофон',exact=True).click()
            expect(page.get_by_role('heading',name='Я вас слушаю',exact=True)).to_be_visible()
            voice_routes[-1].send('{"type":"speech_started","turn":1}')
            expect(page.get_by_role('heading',name='Говорите, я слушаю…',exact=True)).to_be_visible()
            voice_routes[-1].send('{"type":"result","turn":1,"data":{"response":"Тест звука","trace":{"transcript":"Привет"},"audio_url":"/api/audio/test"}}')
            expect(page.get_by_role('heading',name='Отвечаю вам…',exact=True)).to_be_visible()
            voice_routes[-1].send('{"type":"speech_started","turn":2}')
            expect(page.get_by_role('heading',name='Говорите, я слушаю…',exact=True)).to_be_visible()
            voice_routes[-1].send('{"type":"error","message":"Повторите фразу"}')
            expect(page.get_by_role('heading',name='Я вас слушаю',exact=True)).to_be_visible()
            page.get_by_role('button',name='Выключить микрофон',exact=True).click()
            expect(page.get_by_role('heading',name='Готова вас слушать',exact=True)).to_be_visible()
            page.get_by_role('button',name='Прослушать ещё раз',exact=True).click()
            expect(page.get_by_role('heading',name='Отвечаю вам…',exact=True)).to_be_visible()
            expect(page.get_by_role('heading',name='Готова вас слушать',exact=True)).to_be_visible(timeout=7000)
            page.get_by_role('button',name='Озвучивание',exact=True).click()
            page.get_by_role('button',name='Где найти переводы?',exact=True).click()
            page.get_by_role('button',name='Да, покажи',exact=True).click()
            expect(page.get_by_role('dialog')).to_be_visible()
            page.get_by_role('button',name='Далее →',exact=True).click()
            expect(page.get_by_role('heading',name='Перейдите в «Переводы»')).to_be_visible()
            page.get_by_role('button',name='Закрыть',exact=True).click()
            expect(page.get_by_role('dialog')).not_to_be_visible()
            screenshots=ROOT/'reports';screenshots.mkdir(exist_ok=True)
            page.evaluate('window.scrollTo(0, 0)')
            page.screenshot(path=str(screenshots/'platform-desktop.png'),full_page=True)
            page.get_by_role('button',name='ENG',exact=True).click()
            expect(page.get_by_role('heading',name='Hello! I’m here to help.')).to_be_visible()
            page.get_by_role('button',name='Where can I find transfers?',exact=True).click()
            page.get_by_role('button',name='Yes, show me',exact=True).click()
            expect(page.get_by_role('heading',name='Transfer by phone number')).to_be_visible()
            page.get_by_role('button',name='Close',exact=True).click()
            page.get_by_role('button',name='РУС',exact=True).click()
            page.get_by_role('button',name='История разговоров',exact=True).click()
            expect(page.locator('.messages')).to_be_visible()
            page.get_by_role('button',name='Удалить историю',exact=True).click()
            page.get_by_role('dialog').get_by_role('button',name='Удалить историю',exact=True).click()
            expect(page.locator('.empty-state')).to_be_visible()
            page.get_by_role('button',name='Голосовой помощник',exact=True).click()
            page.set_viewport_size({'width':390,'height':844})
            page.evaluate('window.scrollTo(0, 0)')
            page.screenshot(path=str(screenshots/'platform-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Mobile horizontal overflow'
            page.get_by_role('button',name='Мой аккаунт',exact=True).click()
            page.get_by_label('Текущий пароль',exact=True).fill('ui-check-password-2026')
            page.get_by_label('Новый пароль — от 12 символов',exact=True).fill('updated-ui-password-2026')
            page.get_by_label('Повторите новый пароль',exact=True).fill('updated-ui-password-2026')
            page.get_by_role('button',name='Изменить пароль',exact=True).click()
            expect(page.get_by_role('status')).to_contain_text('Пароль изменён')
            page.get_by_role('button',name='Выйти на всех устройствах',exact=True).click()
            expect(page.get_by_role('heading',name='Рады вас видеть')).to_be_visible()
            assert not errors,errors
            browser.close()
            print('UI PASS: registration, PCM playback/replay, microphone, interruption, error recovery, consent, slides, languages, history deletion, password change, logout, desktop/mobile; no page errors')
    finally:
        process.terminate();process.wait(timeout=10)
