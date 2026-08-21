# test_telegram_push.py
import telegram_push as tp

def test_load_bot_token(tmp_path):
    p = tmp_path / "bot.env"
    p.write_text('TELEGRAM_BOT_TOKEN="123:ABC"\nOTHER=x\n')
    assert tp.load_bot_token(str(p)) == "123:ABC"

def test_push_approval_sends_doc_and_buttons(tmp_path):
    doc = tmp_path / "list.txt"; doc.write_text("liste")
    calls = []
    def fake_sender(method, params):
        calls.append((method, params))
    tp.push_approval("T", 8311805232, "🟢 film — 79 Änderungen",
                     str(doc), "APPROV", sender=fake_sender)
    methods = [m for m, _ in calls]
    assert "sendDocument" in methods
    assert "sendMessage" in methods
    msg = next(p for m, p in calls if m == "sendMessage")
    kb = msg["reply_markup"]["inline_keyboard"][0]
    datas = {btn["callback_data"] for btn in kb}
    assert "seo:ok:APPROV" in datas and "seo:no:APPROV" in datas

def test_push_text(tmp_path):
    calls = []
    tp.push_text("T", 1, "⏳ wartet", sender=lambda m, p: calls.append((m, p)))
    assert calls[0][0] == "sendMessage"
    assert calls[0][1]["text"] == "⏳ wartet"
