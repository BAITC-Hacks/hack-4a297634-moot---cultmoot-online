"""Read-only assistance; no connection to customer banking systems."""
import re

def answer(text,scenario,language):
    english=language=='other' and bool(re.search('[a-zA-Z]',text))
    k='en' if english else 'kk' if language=='kk' else 'ru'
    name=(scenario.name_ru if scenario else '')+' '+text
    source='https://halykbank.kz/knowledge_base'
    if re.search('блок|потер|укра|жоғал|бұғат|lost|stolen|block',name,re.I):
        message={'ru':'Если карта потеряна или вы заметили подозрительную операцию, заблокируйте её в официальном приложении Halyk и обратитесь в банк по номеру 7111. Я не имею доступа к вашей карте и не могу заблокировать её за вас.',
          'kk':'Карта жоғалса немесе күмәнді операция байқалса, оны Halyk ресми қосымшасында бұғаттап, 7111 нөмірі арқылы банкке хабарласыңыз. Мен картаңызға қол жеткізе алмаймын және оны бұғаттай алмаймын.',
          'en':'If your card is lost or you notice a suspicious transaction, block it in the official Halyk app and contact the bank at 7111. I cannot access or block your card.'}
    elif re.search('перев|аудар|transfer',name,re.I):
        source='https://halykbank.kz/knowledge_base/3286'
        message={'ru':'Переводы доступны в приложении Halyk в разделе «Переводы». Выберите способ перевода, проверьте получателя, сумму и показанную комиссию. Если не можете найти раздел, попросите меня показать его по шагам.',
          'kk':'Аударымдар Halyk қосымшасының «Аударымдар» бөлімінде қолжетімді. Аудару тәсілін таңдап, алушыны, соманы және көрсетілген комиссияны тексеріңіз. Бөлімді таба алмасаңыз, қадамдап көрсетуді сұраңыз.',
          'en':'Open Transfers in the Halyk app, select a transfer method, and check the recipient, amount and displayed fee. Ask me to show the steps if you cannot find the section.'}
    elif re.search('баланс|остат|қалдық|balance|статус',name,re.I):
        message={'ru':'Актуальный баланс и статус операций доступны в вашем приложении Halyk. Я не подключена к вашим банковским счетам. Откройте нужную карту или счёт и проверьте сведения в официальном приложении.',
          'kk':'Өзекті баланс пен операция мәртебесін Halyk қосымшасынан тексеріңіз. Мен банк шоттарыңызға қосылмағанмын. Қажетті картаны немесе шотты ресми қосымшада ашыңыз.',
          'en':'Check your current balance and transaction status in the official Halyk app. I am not connected to your bank accounts. Open the relevant card or account in the app.'}
    else:
        message={'ru':'Помогу сориентироваться в приложении Halyk и найти официальную информацию. Уточните, что вас интересует: карты, переводы, платежи или вклады? Актуальные условия и действия со счётом доступны в официальном приложении и на сайте банка.',
          'kk':'Halyk қосымшасында қажетті бөлім мен ресми ақпаратты табуға көмектесемін. Сізді карта, аударым, төлем немесе депозит қызықтыра ма? Өзекті шарттар мен шот операциялары банктің ресми қосымшасы мен сайтында қолжетімді.',
          'en':'I can help you navigate Halyk and find official information. Are you asking about cards, transfers, payments or deposits? Current terms and account operations are available in the official app and bank website.'}
    return message[k],{'source':source,'bank_connected':False,'read_only':True}
