import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app.core.config import settings


def send_verification_email(
    recipient_email: str,
    verification_code: str
):
    message = MIMEMultipart()

    message["From"] = settings.SMTP_FROM
    message["To"] = recipient_email
    message["Subject"] = "StudyFlow AI - E-posta Doğrulama Kodu"

    body = f"""
Merhaba,

StudyFlow AI hesabınızı doğrulamak için aşağıdaki kodu kullanın:

{verification_code}

Bu kod 10 dakika boyunca geçerlidir.

Eğer bu işlemi siz başlatmadıysanız bu e-postayı dikkate almayabilirsiniz.

StudyFlow AI
"""

    message.attach(
        MIMEText(body, "plain", "utf-8")
    )

    with smtplib.SMTP_SSL(
        settings.SMTP_HOST,
        settings.SMTP_PORT
    ) as server:

        server.login(
            settings.SMTP_USERNAME,
            settings.SMTP_PASSWORD
        )

        server.sendmail(
            settings.SMTP_FROM,
            recipient_email,
            message.as_string()
        )


def send_password_reset_email(
    recipient_email: str,
    reset_link: str
):
    message = MIMEMultipart()

    message["From"] = settings.SMTP_FROM
    message["To"] = recipient_email
    message["Subject"] = "StudyFlow AI - Şifre Sıfırlama"

    body = f"""
Merhaba,

StudyFlow AI hesabınız için bir şifre sıfırlama isteği aldık.

Şifrenizi sıfırlamak için aşağıdaki bağlantıya tıklayın:

{reset_link}

Bu bağlantı 30 dakika boyunca geçerlidir ve yalnızca bir kez kullanılabilir.

Eğer bu işlemi siz başlatmadıysanız bu e-postayı dikkate almayabilirsiniz.

StudyFlow AI
"""

    message.attach(
        MIMEText(body, "plain", "utf-8")
    )

    with smtplib.SMTP_SSL(
        settings.SMTP_HOST,
        settings.SMTP_PORT
    ) as server:

        server.login(
            settings.SMTP_USERNAME,
            settings.SMTP_PASSWORD
        )

        server.sendmail(
            settings.SMTP_FROM,
            recipient_email,
            message.as_string()
        )