#!/usr/bin/env python3
"""
邮件 HTML5 模板 + 垃圾词检测
"""
import re

# ═══ 垃圾邮件触发词库 ═══
SPAM_TRIGGER_WORDS = {
    "free", "buy now", "click here", "click below", "limited time", "act now",
    "100%", "guarantee", "winner", "cash", "credit card", "best price",
    "cheap", "discount", "earn money", "extra income", "fast cash",
    "for free", "free access", "free money", "free trial", "get it now",
    "giving away", "increase sales", "increase traffic", "lowest price",
    "make money", "money back", "no cost", "no fees", "no obligation",
    "offer expires", "once in a lifetime", "one time", "order now",
    "please read", "risk free", "satisfaction guaranteed", "save big",
    "save up to", "special promotion", "this won't last", "unlimited",
    "urgent", "while supplies last", "work from home", "you have been selected",
    "double your", "earn per week", "expect to earn", "fantastic deal",
    "for instant access", "hidden charges", "million dollars", "not spam",
    "pure profit", "refinance", "removes wrinkles", "reverses aging",
    "serious cash", "stop snoring", "trial offer", "unsecured credit",
}


def check_spam_score(subject, body_text):
    """检测邮件垃圾词风险"""
    full_text = (subject + " " + body_text).lower()
    warnings = []
    suggestions = []
    score = 0

    found_triggers = [w for w in SPAM_TRIGGER_WORDS if w in full_text]
    if found_triggers:
        score += len(found_triggers) * 2
        warnings.append("检测到 %d 个垃圾触发词: %s" % (len(found_triggers), ", ".join(found_triggers[:5])))
        suggestions.append("移除营销用语，使用专业商务措辞")

    caps_words = re.findall(r'\b[A-Z]{5,}\b', body_text)
    if len(caps_words) > 3:
        score += 1
        warnings.append("检测到 %d 个全大写词（垃圾邮件特征）" % len(caps_words))

    exclaim_count = body_text.count("!")
    if exclaim_count > 3:
        score += 1
        warnings.append("感叹号过多 (%d个)" % exclaim_count)

    link_count = len(re.findall(r'https?://', body_text))
    if link_count > 3:
        score += 1
        warnings.append("链接过多 (%d个)" % link_count)

    if re.search(r'^(re:|fwd:|fw:)\s', subject, re.IGNORECASE):
        score += 3
        warnings.append("主题行伪装成回复/转发")

    text_only = re.sub(r'<[^>]+>', '', body_text).strip()
    img_count = len(re.findall(r'<img[^>]+>', body_text))
    if img_count > 0 and len(text_only) < 100:
        score += 2
        warnings.append("图片多但文字少")

    if len(body_text.strip()) < 50:
        score += 1
        warnings.append("正文过短")

    if score >= 8:
        level = "high"
    elif score >= 4:
        level = "medium"
    else:
        level = "low"

    verdicts = {
        "low": "OK - low risk / 通过，风险低",
        "medium": "WARNING - needs revision / 建议修改",
        "high": "DANGER - likely spam / 高风险，可能进垃圾箱"
    }

    return {
        "score": min(10, score),
        "level": level,
        "warnings": warnings,
        "suggestions": suggestions,
        "trigger_words_found": found_triggers[:5],
        "verdict": verdicts.get(level, "")
    }


def build_html_email(subject, body_text, company_name="", sender_info=None):
    """
    将纯文本邮件转为 HTML5 格式
    """
    if sender_info is None:
        sender_info = {}

    sender_name = sender_info.get("name", "Sales Team")
    sender_company = sender_info.get("company", "Atlas Auto Parts")
    sender_website = sender_info.get("website", "")
    sender_email = sender_info.get("email", "")

    body_text_clean = body_text.strip()
    paragraphs = [p.strip() for p in body_text_clean.split("\n") if p.strip()]

    html_paragraphs = ""
    for p in paragraphs:
        if p.startswith(("Best regards", "Sincerely", "Regards", "Thanks", "Thank you")):
            html_paragraphs += '\n            <p style="margin-top:24px;color:#444444">%s</p>' % p
        else:
            html_paragraphs += '\n            <p style="margin:0 0 12px 0;line-height:1.7;color:#333333">%s</p>' % p

    unsubscribe_url = "mailto:%s?subject=Unsubscribe" % sender_email if sender_email else "#"

    # CTA section
    cta_section = ""
    if sender_website:
        cta_section = """
                    <tr>
                        <td style="padding:0 32px 24px 32px;text-align:center">
                            <a href="%s" style="display:inline-block;padding:12px 28px;background-color:#1a1a2e;color:#ffffff;text-decoration:none;border-radius:6px;font-size:14px;font-weight:600">View Our Product Catalog &rarr;</a>
                        </td>
                    </tr>""" % sender_website

    greeting = company_name if company_name else "Sir/Madam"

    body_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>%s</title>
</head>
<body style="margin:0;padding:0;background-color:#f5f5f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif">
    <table role="presentation" width="100%%" cellpadding="0" cellspacing="0" style="background-color:#f5f5f5;padding:20px 0">
        <tr>
            <td align="center">
                <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.06)">
                    <tr>
                        <td style="background:linear-gradient(135deg,#1a1a2e 0%%,#16213e 100%%);padding:28px 32px;text-align:center">
                            <div style="font-size:20px;font-weight:700;color:#ffffff;letter-spacing:0.5px">%s</div>
                            <div style="font-size:13px;color:rgba(255,255,255,0.7);margin-top:4px">Professional Auto Parts Supplier</div>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:24px 32px 0 32px">
                            <h1 style="margin:0;font-size:18px;font-weight:600;color:#1a1a2e;line-height:1.4">%s</h1>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:4px 32px 0 32px">
                            <p style="font-size:14px;color:#666666;margin:0">Dear %s,</p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:16px 32px 24px 32px;font-size:15px;line-height:1.7;color:#333333">
                            %s
                        </td>
                    </tr>
                    %s
                    <tr>
                        <td style="padding:0 32px">
                            <hr style="border:none;border-top:1px solid #eeeeee;margin:0">
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:20px 32px 28px 32px;font-size:12px;color:#999999;line-height:1.6">
                            <p style="margin:0 0 4px 0"><strong>%s</strong> &middot; %s</p>
                            %s
                            %s
                            <p style="margin:16px 0 0 0;font-size:11px;color:#bbbbbb">
                                This is a B2B business inquiry. If you prefer not to receive further communications, 
                                please <a href="%s" style="color:#999999">reply with "unsubscribe"</a>.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>""" % (
        subject,
        sender_company,
        subject,
        greeting,
        html_paragraphs,
        cta_section,
        sender_name, sender_company,
        '<p style="margin:0 0 4px 0">Email: %s</p>' % sender_email if sender_email else "",
        '<p style="margin:0 0 4px 0">Web: %s</p>' % sender_website if sender_website else "",
        unsubscribe_url
    )

    headers = {
        "MIME-Version": "1.0",
        "Content-Type": "text/html; charset=UTF-8",
        "X-Mailer": "Atlas Customer Development Engine",
        "X-Priority": "3",
        "Precedence": "bulk",
        "List-Unsubscribe": "<mailto:%s?subject=Unsubscribe>" % sender_email if sender_email else "",
    }

    return {
        "subject": subject,
        "body_text": body_text_clean,
        "body_html": body_html,
        "headers": headers
    }
