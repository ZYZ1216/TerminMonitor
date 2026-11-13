import os
import time
from dotenv import load_dotenv
import requests
from playwright.sync_api import sync_playwright

load_dotenv()

# 💡 从环境变量读取秘钥（云端运行由 GitHub Secrets 提供，本地测试可保底）
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# 🚨 正式部署：关闭测试模式，只有真正检测到 Nächster Termin 时才发送推送
TEST_TG_NOTIFICATION = False


def send_telegram(message):
    """发送 Telegram 消息通知（高优先级响铃版）"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ 未配置有效的 Telegram Bot Token 或 Chat ID，跳过推送")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_notification": False,  # 强制响铃 + 横幅弹窗
    }

    try:
        response = requests.post(url, json=data, timeout=10)
        res_json = response.json()
        if res_json.get("ok"):
            print("📱 Telegram 通知已成功发送到手机！")
        else:
            print(f"⚠️ Telegram 发送失败：{res_json}")
    except Exception as e:
        print(f"⚠️ 发送 Telegram 通知时出错: {e}")


def safe_click(locator, name, timeout=8000):
    """带日志和超时的安全点击函数"""
    print(f"  👉 尝试点击: {name}...")
    locator.wait_for(state="visible", timeout=timeout)
    locator.click()


def check_termin_once(page):
    """执行一次完整的检查流程"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n[{timestamp}] 🔍 开始检查...")

    # 1. 访问/刷新页面
    print("  🌐 打开网页...")
    page.goto("https://terminvergabe.muelheim-ruhr.de/?rs", wait_until="domcontentloaded")

    # 2. 柔性处理 Cookie
    try:
        cookie_btn = page.get_by_role("button", name="Ablehnen")
        if cookie_btn.is_visible(timeout=3000):
            cookie_btn.click()
            print("  🍪 已拒绝 Cookie 弹窗")
    except Exception:
        print("  ℹ️ 未检测到 Cookie 弹窗，直接继续")

    # 3. 逐步点击进入业务流程
    safe_click(page.get_by_role("button", name="Ausländeramt"), "Ausländeramt")
    safe_click(
        page.get_by_role("tab", name="Studierende und Anerkennung"),
        "Studierende und Anerkennung 标签",
    )
    safe_click(
        page.get_by_role(
            "button",
            name="Erhöhen der Anzahl des Anliegens Verlängerung Aufenthaltserlaubnis",
        ),
        "+1 延签按钮",
    )
    safe_click(page.get_by_role("button", name="Weiter"), "Weiter (下一步)")

    # 4. 勾选所有材料清单
    print("  📋 正在勾选材料清单...")
    page.get_by_title("Gültiger Nationalpass").click()
    page.get_by_title("Aktuelle Aufenthaltserlaubnis").click()
    page.get_by_title("Vollständig ausgefüllter").click()
    page.get_by_title("Krankenversicherungsnachweis").click()
    page.get_by_title("Nachweis über Sicherstellung").click()
    page.get_by_title("ggf. Anmeldung zum Sprachkurs").click()
    page.get_by_title("ggf. Defizitbescheinigung").click()
    page.get_by_title("ggf. Vierbescheinigung").click()
    page.locator("div").filter(has_text="ggf. unterschriebener und").nth(5).click()
    page.get_by_title("ggf. Zulassungsbescheinigung").click()
    page.get_by_title("ggf. vollständig ausgefüllte").click()
    page.get_by_title("ggf. Übersicht aller").click()
    page.get_by_title("ggf. Hochschulabschluss").click()
    page.get_by_title("bei ausländischen Abschlüssen").click()
    page.get_by_title("Bearbeitungsgebühren über 93 €").click()

    # 5. 提交进入结果页
    safe_click(
        page.get_by_role("button", name="Weiter", description="OK"),
        "确认材料并提交",
    )

    time.sleep(2)

    # 6. 检测卡片文本内容
    print("  🧐 正在检测是否有 Nächster Termin...")
    card_element = page.locator("div").filter(has_text="Ausländeramt").last
    card_text = card_element.inner_text()

    if TEST_TG_NOTIFICATION or "Nächster Termin" in card_text:
        msg = (
            "🚨 <b>Mülheim 外国人局有预约放号啦！</b>\n\n"
            "请尽快登录官网预约：\nhttps://terminvergabe.muelheim-ruhr.de/?rs"
        )
        send_telegram(msg)
        return True, "有预约放出！已发送通知！"
    else:
        return False, "目前无号 (未检测到 Nächster Termin)"


def run():
    """云端/单次运行入口"""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="de-DE",
        )
        page = context.new_page()

        try:
            has_termin, msg = check_termin_once(page)
            print(f"📌 运行结果: {msg}")
        except Exception as e:
            print(f"⚠️ 本轮检查出现异常: {e}")
        finally:
            browser.close()


if __name__ == "__main__":
    run()