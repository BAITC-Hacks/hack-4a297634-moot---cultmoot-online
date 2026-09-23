import json

class Knowledge:
    def __init__(self,path,enabled=True):
        self.data=json.loads(path.read_text(encoding='utf-8')) if enabled else {}

    def answer(self,sid,lang):
        fallback={'ru':'У меня нет подтверждённых данных для такого ответа. Передайте вопрос сотруднику банка.',
                  'kk':'Бұл жауапқа расталған деректерім жоқ. Банк қызметкеріне хабарласыңыз.'}
        return self.data.get(sid,fallback).get(lang,fallback[lang])
