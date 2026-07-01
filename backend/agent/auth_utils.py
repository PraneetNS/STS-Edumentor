import jwt
import bcrypt
import uuid
import time
import asyncio
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import Config

logger = logging.getLogger("edumentor.agent.auth_utils")

def hash_password(password: str) -> str:
    """Hash password using bcrypt with cost factor 12."""
    salt = bcrypt.gensalt(rounds=12)
    # bcrypt requires bytes
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def check_password(password: str, password_hash: str) -> bool:
    """Verify raw password against stored bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except Exception as e:
        logger.error("Password verification error: %s", e)
        return False

def generate_access_token(user_id: uuid.UUID, email: str) -> str:
    """Generate a short-lived access JWT (15 minutes)."""
    payload = {
        "user_id": str(user_id),
        "email": email,
        "type": "access",
        "exp": time.time() + 900 # 15 minutes
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm=Config.JWT_ALGORITHM)

def generate_refresh_token(user_id: uuid.UUID, email: str) -> str:
    """Generate a long-lived refresh JWT (7 days)."""
    payload = {
        "user_id": str(user_id),
        "email": email,
        "type": "refresh",
        "exp": time.time() + (7 * 86400) # 7 days
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm=Config.JWT_ALGORITHM)

def generate_verification_token(email: str) -> str:
    """Generate a 24-hour verification token for email registration."""
    payload = {
        "email": email,
        "type": "verification",
        "exp": time.time() + 86400 # 24 hours
    }
    return jwt.encode(payload, Config.JWT_SECRET, algorithm=Config.JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    """
    Decode and verify a JWT.
    Raises jwt.ExpiredSignatureError or jwt.InvalidTokenError on failure.
    """
    return jwt.decode(token, Config.JWT_SECRET, algorithms=[Config.JWT_ALGORITHM])

def send_verification_email_sync(email: str, token: str):
    """SMTP email sending helper (runs in worker thread)."""
    host = Config.SMTP_HOST
    port = Config.SMTP_PORT
    user = Config.SMTP_USER
    password = Config.SMTP_PASSWORD
    sender = Config.SMTP_FROM

    # Construct the link to backend verify-email endpoint
    verify_link = f"http://localhost:8000/auth/verify-email?token={token}"

    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = email
    msg['Subject'] = "Verify your EduMentor account"

    body = f"""Hello,

Thank you for registering at EduMentor! Please verify your account by clicking the link below:

{verify_link}

This link is valid for 24 hours. If you did not request this, please ignore this email.

Regards,
EduMentor Team"""
    
    msg.attach(MIMEText(body, 'plain'))

    logger.info("Connecting to SMTP server at %s:%d...", host, port)
    
    # Send verification link directly to console for easy development/testing bypass
    print(f"\n[DEVELOPER BYPASS] Verification link for {email}:\n{verify_link}\n")

    # Only send actual email if SMTP_HOST is not 'localhost' or we have custom configuration
    if not (host == "localhost" and port == 1025 and not user):
        try:
            with smtplib.SMTP(host, port) as server:
                if port == 587:
                    server.starttls()
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
            logger.info("Verification email sent successfully to %s", email)
        except Exception as exc:
            logger.error("Failed to send SMTP email: %s", exc)
    else:
        logger.info("Using developer local SMTP bypass. Link logged to stdout.")

async def send_verification_email(email: str, token: str):
    """Asynchronous wrapper for verification email sending."""
    await asyncio.to_thread(send_verification_email_sync, email, token)
