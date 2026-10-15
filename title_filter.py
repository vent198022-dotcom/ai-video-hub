"""標題過濾：在影片入庫前排除注定不會上架的內容，省下 AI 分類額度。

網站只收中文（繁體或簡體）教學，且不收廣東話影片。實測 9 月以來被 AI 排除的
影片有七成以上標題完全沒有中文字，這些不必再送去分類。

規則依序判斷，回傳第一個命中的原因：
- 非中文：標題沒有任何中日韓統一表意文字
- 日文：用了日文助詞（を、で、は、が、に、と、も），或假名字母至少 2 個且
  不少於漢字數的三分之一。「の」與「・」「ー」常被中文標題借用，不單獨作數；
  頻道名夾少量假名的中文標題（如「｜すごい知識站」）也不會被誤判
- 廣東話：含粵語特有用字，或直接標示「廣東話」「粵語」
"""
import re

_HAN = re.compile(r"[一-鿿]")
_KANA = re.compile(r"[\u3041-\u3096\u30a1-\u30fa]")
_JA_PARTICLES = re.compile(r"[をではがにとも]")

# 只收國語幾乎不會用到的粵語字，以標題實測校正過誤判：
# 「咪」會誤中「貓咪」、「揀」是國語常用字（揀花生）、「咩」在台灣網路用語是語尾，
# 因此都不列入
_CANTONESE = re.compile(
    r"廣東話|粵語|[嘅咗喺唔冇啲嚟佢哋嘢嗰睇搵啱攞噉乜冧畀嘞喎]"
)


def reject_reason(title):
    """標題該被排除時回傳原因（非中文／日文／廣東話），否則回傳 None。"""
    title = title or ""
    if not _HAN.search(title):
        return "非中文"
    if _is_japanese(title):
        return "日文"
    if _CANTONESE.search(title):
        return "廣東話"
    return None


def _is_japanese(title):
    if _JA_PARTICLES.search(title):
        return True
    kana = len(_KANA.findall(title))
    return kana >= 2 and kana * 3 >= len(_HAN.findall(title))
