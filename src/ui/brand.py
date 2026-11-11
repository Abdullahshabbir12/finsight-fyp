"""BrokerLens visual identity: palette, logo mark, skyline artwork and the HTML blocks built from them."""
from html import escape

GREEN_900 = "#12332a"  # sidebar and hero panels
GREEN_700 = "#1d4a3b"  # primary actions, chart totals
GREEN_500 = "#3f8f6b"
GREEN_100 = "#e4efe8"
CREAM = "#e9e3d4"
RUST = "#b5523b"  # decreases in charts
STONE = "#a9a596"  # calculated chart steps
SERIF = "'Libre Caslon Text', Georgia, serif"


def sparkle(x: float, y: float, r: float, colour: str) -> str:
    """A four-point star: the accent beside the B."""
    return (f'<path d="M{x} {y - r} Q{x} {y} {x + r} {y} Q{x} {y} {x} {y + r} Q{x} {y} {x - r} {y} Q{x} {y} {x} {y - r}Z" '
            f'fill="{colour}"/>')


def mark(size: int = 44, colour: str = CREAM) -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
            f'<text x="6" y="35" font-family="{SERIF}" font-size="36" fill="{colour}">B</text>'
            f'{sparkle(34, 9, 5.5, colour)}{sparkle(40, 17, 2.2, colour)}</svg>')


# Office towers and a minaret-like spire, low contrast; decoration only, never data.
SKYLINE = (
    '<svg class="bl-skyline" viewBox="0 0 600 220" preserveAspectRatio="xMaxYMax slice" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
    '<g fill="#ffffff" fill-opacity="0.07">'
    '<rect x="20" y="120" width="46" height="100"/><rect x="72" y="90" width="38" height="130"/>'
    '<rect x="118" y="135" width="52" height="85"/><rect x="178" y="70" width="44" height="150"/>'
    '<rect x="230" y="105" width="36" height="115"/><rect x="274" y="140" width="58" height="80"/>'
    '<rect x="340" y="60" width="40" height="160"/><rect x="388" y="95" width="50" height="125"/>'
    '<rect x="446" y="125" width="42" height="95"/><rect x="496" y="85" width="34" height="135"/>'
    '<rect x="538" y="115" width="56" height="105"/></g>'
    '<g fill="#ffffff" fill-opacity="0.12">'
    '<path d="M300 220 V58 L312 40 L318 6 L324 40 L336 58 V220 Z"/>'
    '<rect x="196" y="40" width="30" height="180"/><rect x="420" y="48" width="26" height="172"/></g>'
    '<g fill="#ffffff" fill-opacity="0.18">'
    + "".join(f'<rect x="{x}" y="{y}" width="3" height="5"/>' for x in (184, 192, 200, 208, 346, 354, 362, 370)
              for y in range(80, 210, 14)) +
    '</g></svg>')


def side_brand() -> str:
    return (f'<div class="bl-side-brand">{mark(40)}<div><div class="bl-word">BrokerLens</div>'
            '<div class="bl-tag">AI-assisted financial analysis</div></div></div>')


def login_panel() -> str:
    return (f'<div class="bl-login-panel">{SKYLINE}<div class="bl-login-inner">{mark(72)}'
            '<div class="bl-login-word">BrokerLens</div><div class="bl-login-tag">AI-assisted financial analysis</div>'
            '<div class="bl-rule"></div><div class="bl-login-quote">Smarter analysis.<br>Clearer decisions.</div></div></div>')


def hero(title: str, subtitle: str) -> str:
    return (f'<div class="bl-hero">{SKYLINE}<div class="bl-hero-text"><h1>{escape(title)}</h1>'
            f'<p>{escape(subtitle)}</p></div></div>')


def stat_cards(items: list[tuple[str, str, str]]) -> str:
    """(material icon name, value, label) cards in one responsive row."""
    cards = "".join(f'<div class="bl-stat"><span class="material-symbols-rounded">{icon}</span>'
                    f'<div class="bl-stat-value">{escape(value)}</div><div class="bl-stat-label">{escape(label)}</div></div>'
                    for icon, value, label in items)
    return f'<div class="bl-stats">{cards}</div>'
