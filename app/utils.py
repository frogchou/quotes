import io
import re
import base64
import qrcode
from fastapi.responses import JSONResponse


def json_error(code: str, message: str, status_code: int = 400):
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


def generate_qr_data_uri(url: str) -> str:
    qr = qrcode.QRCode(box_size=3, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    base64_img = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{base64_img}"


def highlight_text(text: str, keyword: str) -> str:
    if not keyword:
        return text
    pattern = re.compile(re.escape(keyword), re.IGNORECASE)
    return pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", text)
