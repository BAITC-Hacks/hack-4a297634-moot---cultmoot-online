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

scratch=ROOT.parents[1]/'work'
scratch.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=scratch) as tmp:
    env=os.environ.copy();env['HV_TEST_DATABASE']=str(Path(tmp)/'ui.sqlite3')
    process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--server'],cwd=ROOT,env=env)
    try:
        for attempt in range(100):
            try:
                if httpx.get('http://127.0.0.1:8011/health/live').status_code==200:break
            except httpx.HTTPError:time.sleep(.1)
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,channel=os.getenv('HV_BROWSER_CHANNEL','msedge'))
            page=browser.new_page(viewport={'width':1440,'height':1040})
            errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            # Test audio requests locally; never send provider API requests in UI checks.
            page.route('**/api/audio/**',lambda route:route.fulfill(status=200,content_type='audio/mpeg',body=b''))
            page.goto('http://127.0.0.1:8011/register')
            page.get_by_label('Email / Gmail').fill('ui-check@example.invalid')
            page.get_by_label('Пароль',exact=True).fill('ui-check-password-2026')
            page.get_by_role('button',name='Создать аккаунт →',exact=True).click()
            expect(page.get_by_role('heading',name='Здравствуйте! Я рядом.')).to_be_visible()
            page.get_by_role('button',name='Озвучивание',exact=True).click()
            page.get_by_role('button',name='Где найти переводы?',exact=True).click()
            page.get_by_role('button',name='Да, покажи',exact=True).click()
            expect(page.get_by_role('dialog')).to_be_visible()
            page.get_by_role('button',name='Далее →',exact=True).click()
            expect(page.get_by_role('heading',name='Перейдите в «Переводы»')).to_be_visible()
            page.get_by_role('button',name='Закрыть',exact=True).click()
            expect(page.get_by_role('dialog')).not_to_be_visible()
            screenshots=ROOT/'reports';screenshots.mkdir(exist_ok=True)
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
            print('UI PASS: registration, consent, slides, languages, history deletion, password change, logout, desktop/mobile; no page errors')
    finally:
        process.terminate();process.wait(timeout=10)
