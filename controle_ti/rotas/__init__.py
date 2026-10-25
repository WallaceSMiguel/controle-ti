from datetime import date, datetime


def data_form(valor: str | None) -> str | None:
    """Valida data AAAA-MM-DD vinda de <input type=date>."""
    valor = (valor or "").strip()
    if not valor:
        return None
    try:
        return date.fromisoformat(valor).isoformat()
    except ValueError:
        return None


def txt(form, campo, limite=500) -> str:
    return (form.get(campo) or "").strip()[:limite]


def dias_desde(data_hora: str) -> int:
    try:
        return (datetime.now() - datetime.strptime(data_hora[:19], "%Y-%m-%d %H:%M:%S")).days
    except (ValueError, TypeError):
        return 0
