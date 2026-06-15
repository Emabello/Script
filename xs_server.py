"""
xs_server.py — Calendario settimanale per XS (gira in locale nel browser).

Vista a blocchi della settimana, dettaglio del giorno con note per ogni
inserimento, cancellazione, riepilogo settimanale per cliente, tema
chiaro/scuro e gestione utente. Si appoggia al motore in xs_client.py.

Dipendenze:
  pip install requests beautifulsoup4 flask
Avvio:
  py xs_server.py          (oppure imposta XS_USER / XS_PASS prima)
Poi apri:  http://127.0.0.1:5000
"""

import datetime as dt
import os
from datetime import timedelta
from flask import Flask, request, jsonify, Response, session
from xs_client import XSClient, _get_credentials

app = Flask(__name__)
client = XSClient()

import base64, socket
ICON_192 = base64.b64decode('''iVBORw0KGgoAAAANSUhEUgAAAMAAAADACAYAAABS3GwHAAAGb0lEQVR4nO3cS3ITQRCE4ZKDLQs4EzchOBXBTTiTWfgAsHAIyZJG09Nd/ais/9uDZ3oyu3rkx8kW8/nrl7+zrwH9vL3+Oc2+hmtTL4aww2xuKYZ/YUKPZ0aXYdgXI/g4YlQRun8Rgo8WvYvQ7T8n+PDUqwju/ynBR0/eRXjx/M8IP3rzzphLmwg+ZvCYBs0TgPBjFo/sNRWA8GO21gxWF4DwYxUtWawqAOHHamozebgAhB+rqsnmoQIQfqzuaEaLC0D4EcWRrBYVgPAjmtLM7haA8COqkuy6/igEEM3TArD7I7q9DG8WgPBDxbMscwRCag8LwO4PNVuZZgIgtbsCsPtD1aNsMwGQ2ocCsPtD3W3GmQBI7X8B2P2RxXXWmQBIjQIgtRczjj/I55x5JgBSowBIjQIgNQqA1E68ACMzJgBSowBI7dPsC8jg98/v1f/2249fjleCW7wDOGsJeylK4YcCNBoR+D0Uoh4FqLBC6LdQhmMoQKGVQ7+FMuyjADsiBv8WRdhGATYoBP8WRbhHAW4oBv8WRbigAFd6hb8lcCtekxIKYL4hGxGsaNe7svQF8AjTzBBFv/7Z0hagNTgrhkbxnnpLWQD1n81Rvz9P6QpQG46Iwch0r7VSFaAmEAphyHrfJVIUgAC8Yx3uyf9CDA/9oua+1L8xKD0Bjj481eA/wtq8k50APODnjt6v6iSQLcAR2cJ/lvW+r0kegUp3KwJwkXXN5Aqw+oPcu74IP1ahVAKpI1DGB+ipdF2U3gdkCkD4fWQrgUwBShD+MpnWSaIAKrtRNArrHr4AHH36yHIUCl+AEoS/ToZ1C12Akt0nw0PsqWT9Ik+BsAWIvOiKoj6PsAUowe7vQ3kdQxaAo894qkehkAUAvIQrALv/PIpTIFwBAE+hCsDuP5/aFAhVAMCbVAHY/cdQWucwBYg0VhHneYUpwB6lXSkClfWWKQBQI0QBooxTfBThuYUowB6VcRyNwrpLFACoRQGQ2vIFWPnv6GB//Vd/D1i+AEBPFACpUQCkRgGQ2tIF4AU4hsgvwksXAOiNAiA1CoDUKMBiVj4vK6IAA5WG+/fP7xRhkE+zLwDbbkvAp17+KEAgj6YCpWhDAYKjFG0ogCCOTuUowEDffvya8nLLlNjGp0CDEby1UIAJtkowqhyU8IIj0CSlJeD7AX1RgMU9Kgql8HP6/PXL39kX8Qw/El3mSCm81yzyM2ICiCg9Oq0cxhkogCiOTmX4FCgRdv97FACpLV+AyL9vmkHkF2CzAAUAeqIASE2iAByD5lBY9xAFWP0cicciPLcQBQB6kSmAwjiORGW9wxQgwjjFRZTnFaYAJVR2pdUprbNUAYCjQhWgZKwq7U4rKlnfKMcfs2AFALyFKwBTYB613d8sYAEATyELwBQYT3H3NwtagFKUwIfyOoYtQMTdRlnU5xG2AGYchUZQPfqchS5AKUpQJ8O6hS9A6e6T4WF6Kl2vyLu/mUABzOI/hKgU1l2iAKWYAmUyrZNMATgK+chy9DmTKYAZJWiVLfxmYgUwowS1MobfLMBfh641868lR5J9neQmQI2s0yDrfV+TLcDR3SpbGI7er+LubyZ8BDqrCbbqwzZjPW7JToCzmoenOg0I/z35CXAtawCy3neJVAUwq9/dIwYi073WSlcAs7YjToRwqN+fp5QFMGs/568YFMV76i1tAc48XnhnBif69c+WvgBmvp/6jAhTtOtdGQW40uvjz5aQrXhNSijADdXvAVwj/BcUYINiEQj+PQqwQ6EIBH8bBSgUsQgEfx8FqLByGQj9MRSg0QplIPT1KICzEYUg8H4owAD8bM66KABSk/+FGOCZl7fXP6fZFwHM8Pb658QEQGoUAKlRAKRGAZDai9n7y8DsCwFGOmeeCYDUKABS+18AjkHI4jrrTACk9qEATAGou804EwCp3RWAKQBVj7LNBEBqDwvAFICarUwzAZDaZgGYAlDxLMtPJwAlQHR7GeYIhNR2C8AUQFQl2S2aAJQA0ZRmtvgIRAkQxZGsHnoHoARY3dGMHn4JpgRYVU02qz4FogRYTW0mqz8GpQRYRUsWm74PQAkwW2sGm78RRgkwi0f2XMPLX5rGCJ6bruuPQjAN0Jt3xroFlmkAT7021+47NkVAi96nimFHFoqAI0Ydp4ef2SkCnhn9Hjn1pZUywGzuhyfLfWpDKbSt9knhP9U8n+wbPLniAAAAAElFTkSuQmCC''')
ICON_512 = base64.b64decode('''iVBORw0KGgoAAAANSUhEUgAAAgAAAAIACAYAAAD0eNT6AAATyElEQVR4nO3dS5IktxEFQMyYtlyQZ9JNZDqVTDfRmaQFD0Atxmqmurs++QMQgXBfasPurES8l5HVo2+NkH774/e/Zv8MAFf487//+zb7Z+ArH8okAh7gBwVhDhd9AGEPsI9S0J8L3IHAB7iWQnA9F/QCAh9gLIXgPBfwIKEPEIMycIyLtoPQB4hNGdjOhXpD6APkpAy85uI8IfgB1qAIPOai3BH6AGtTBn5xIZrgB6hGESheAAQ/QG2Vi0DJX1zwA3CvYhEo9QsLfgBeqVQESvyigh+APSoUge+zf4DehD8Ae1XIjmUbToUPD4D+Vt0GLPdLCX4AelitCCz1CkD4A9DLahmzRJtZ7UMBILYVtgHpNwDCH4DRVsie1AVghQ8AgJyyZ1DKFUb2iw7AWjK+Eki3ARD+AESTMZtSFYCMFxiAGrJlVIqVRbaLCkBtGV4JhN8ACH8AssmQXaELQIYLCACPRM+wsAUg+oUDgHciZ1nIAhD5ggHAHlEzLVwBiHqhAOCoiNkWqgBEvEAAcIVoGRemAES7MABwtUhZF6IARLogANBTlMybXgCiXAgAGCVC9k0tABEuAADMMDsDpxWA2b84AMw2MwunFADhDwA/zMrE4QVA+APARzOycWgBEP4A8NjojBxWAIQ/ALw2MiuHFADhDwDbjMrM6f8OAAAwXvcC4OkfAPYZkZ1dC4DwB4BjemdotwIg/AHgnJ5Z6jsAAFBQlwLg6R8ArtErUy8vAMIfAK7VI1svLQDCHwD6uDpjfQcAAAq6rAB4+geAvq7M2ksKgPAHgDGuylyvAACgoNMFwNM/AIx1RfbaAABAQacKgKd/AJjjbAYfLgDCHwDmOpPFXgEAQEGHCoCnfwCI4Wgm2wAAQEG7C4CnfwCI5Ug22wAAQEG7CoCnfwCIaW9G2wAAQEGbC4CnfwCIbU9W2wAAQEGbCoCnfwDIYWtm2wAAQEEKAAAU9LYAWP8DQC5bstsGAAAKelkAPP0DQE7vMtwGAAAKUgAAoKCnBcD6HwBye5XlNgAAUJACAAAFPSwA1v8AsIZnmW4DAAAFKQAAUNCXAmD9DwBreZTtNgAAUJACAAAFKQAAUNCHAuD9PwCs6XPG2wAAQEEKAAAUpAAAQEE/C4D3/wCwtvustwEAgIIUAAAoSAEAgIIUAAAo6HtrvgAIAFXcMt8GAAAKUgAAoCAFAAAKUgAAoCAFAAAKUgAAoCAFAAAK+ubfAACAev42+wcArvOff/2j+3/j7//8d/f/BtCfDQAkMSLcr6IkQHwKAASTKej3UgwgDgUAJlo57LdSCmAOBQAGEvjvKQQwhgIAHQn88xQC6EMBgAsJ/P4UAriGAgAnCf15lAE4TgGAA4R+PMoA7KMAwEZCPw9lAN5TAOANwZ+XIgDPKQDwgNBfjzIAHykAcEfwr08RgB8UAGiCvyJFgOoUAMoS+twoA1SkAFCO4OcZRYBKFADKEPxspQhQgQLA8gQ/RykCrOz77B8AehL+nOH+YWU2ACzJ4OZqtgGsRgFgKYKf3hQBVqEAsATBz2iKANn5DgDpCX9mcN+RnQ0AaRnAj/V8MnXNH7MNICMFgHSqh1DksPHZxP1s4DMFgFQqBcxKYeJzg3gUAFJYPUAqhobPFOZSAAhvxaAQDl/5nGEsBYDQVgoFYbCdzx36UwAIaZUAMPzPcy9AHwoA4WQf+AZ9P+4NuI4CQChZB7zBPp57Bc5RAAjBMOco9w4cowAwXbYBbnDH5V6C7RQApso0sA3rPNxX8J4CwDRZhrQBnZd7DJ5TABjOUGY09xx8pQAwVIZBbAivy/0HvygADBN9+Bq8dbgXQQFgkMgD17Cty31JZQoA3UUdsgYsN+5RKlIA6CriYDVUecb9SiXfZ/8ArMswJZuI90fEc8QabADoItrQijjYic09zOpsALicwckKot030c4V+dkAcKlIQyraACcv9zUrsgHgMoYkq4p0P0U6Z+RmA8AlogylSIOaNbnXWYUNAKcZiFQS5T6Lcu7ISwHglChDKMpQpoYo91uU80dOXgFwWIThE2UQU5dzQFY2ABxi6MEPEe7DCOeRfBQAdoswbCIMXbiJcD9GOJfk4hUAu8weMhEGLbzijJCFDQCbGWzw3uz7dPY5JQ8FgBRmD1XYw/1KBgoAm8x8qjBMyWjmfWsLwBYKAG8JfzhGCSAyXwLkJeGfT8/PzGdyjHNERDYAPGVowTVsAohIASAc4c+K3NdEowDw0KynBkOSlc26v20BeEQB4AvhD/0oAUShAPCB8If+lAAiUACYTvhTkfue2RQAfprxdGAIUtmM+98WgBsFgNaa8IdZlABmUQAQ/jCZEsAMCgDDCX/4yrlgNAWguNFPAYYcPDf6fNgC1KYAFObwA+ZAXQoAw3j6h/ecE0ZRAIqy+oe4vApgBAWA7oQ/7Ofc0JsCUJC2D3xmLtSjABRj9Q95eBVATwoA3Qh/OM85ohcFoJCR7d7QguuMPE+2AHUoAABQkAJQhKd/yM0WgKspAFxK+EM/zhdXUgAK0OaBvcyN9SkAi7P6h7V4FcBVFAAuIfxhHOeNKygAC9PegbPMkXUpAJzmaQTGc+44SwFY1KjWbgjBPKPOny3AmhQAAChIAViQp3+owxaAoxQAAChIAeAQT/8Qh/PIEQrAYqzpgF7Ml7UoAOzmaQPicS7ZSwFYiHYO9GbOrEMBYBdPGRCX88keCsAitHJgFPNmDQoAm3m6gPicU7ZSAACgIAVgASPWcZ4qII8R59VrgPwUAAAoSAFIztM/8IgtAO8oAABQkALAS57+IS/nl1cUgMSs34DZzKG8FAAAKEgB4CnrQ8jPOeYZBSApazcgCvMoJwWAhzw1wDqcZx5RAACgIAUgIes2IBpzKR8FgC+sC2E9zjWfKQAAUJACAAAFKQDJ9H7PZk0I6+p9vn0PIBcFAAAKUgAAoCAFgJ+s/2F9zjk3CkAi3q8B0ZlTeSgAAFCQAkBrzVoQKnHeaU0BAICSFIAkvFcDsjCvclAAAKAgBQDvA6Eg5x4FAAAKUgAAoCAFIAFfqAGyMbfiUwAAoCAFoDhfBIK6nP/aFAAAKEgBAICCFAAAKEgBCM43aYGszK/YFAAAKEgBKMw3gAFzoC4FAAAKUgAAoCAFAAAKUgAAoCAFAAAKUgAAoCAFIDD/iAaQnTkWlwJQlL/9BW7Mg5oUAAAoSAGAhfRet1rnwjr+NvsHAK4xKpw//3esjyEnBQA4RSGAnBQAWECk1bxCADkoAEBXCgHEpAAAQz3aVigFMJ4CAMlFWv8fZUsA4ykAQDgKAfSnAADhKQRwPQUASEchgPMUACA9XyyE/RQAYEm2BPCaAgCUoBDARwoAJPf3f/57iT8FHE0hoDoFAKD5HgH1KAAAT9gSsDIFABbgNcAYCgEr+T77BwAAxlMAYBGeRsdyvclOAYCFCCVgKwUAFqMEAFsoAEX5wtjalAD2MA9qUgACM8Q5w/3Tj2u7nWsVlz8DhIXdhu+RJ7z7we0JEdajAEABW8P82dPa5/9dIYD8FAAo5oqVrEIA+SkAwGmVCoF32qxCAQAu9ygkVy4FkJECAAxRaUsAGSgAhf3nX/+wzmSajIVgxfOS4brThwIAhJCxEEBmCkBw/m9eqUohyG/FjclKFAAgBV8shGspAEBaI7cEnmZZjQIALMNrA9hOASjOXwKwMoXgNdejNgUAKMP3COAXBSABfwkA/WzZEtiS7eeaxacAANzx2oAqvs/+AQAi8yTLqhQAPOFAQc49CgAAFKQAJGENCWRhXuWgAABAQQoArTXvA6ES553WFAAAKEkBSMR7NSA6cyoPBYCfrAVhfc45NwoAABSkAABAQQpAMr3fr1kPwrp6n2/v/3NRAACgIAUAAApSAPjCawBYj3PNZwpAQt6zAdGYS/koAABQkALAQ9aFsA7nmUcUgKSs24AozKOcFACe8tQA+TnHPKMAAEBBCkBi1m7AbOZQXgoAL1kfQl7OL68oAABQkAKQ3Ij1m6cIyGfEubX+z00BAICCFIAF2AIA9zz9s4UCAAAFKQBsZgsA8TmnbKUALMI6DhjFvFmDAsAuni4gLueTPRSAhWjlQG/mzDoUAHbzlAHxOJfspQAsRjsHejFf1qIAcIinDYjDeeQIBQAAClIAFjRqTeepA+YbdQ6t/9ejAABAQQrAomwBYH2e/jlDAeA0JQDGc+44SwFYmNYOnGWOrEsB4BKeRmAc540rKACLG9neDSXob+Q58/S/NgWgAIcY2MvcWJ8CwKVsAaAf54srKQBFeBUAuVn9czUFAAAKUgAKsQWAnDz904MCQDdKAJznHNGLAlDM6HZveMFxo8+Pp/9aFICCHHLgM3OhHgWA7mwBYD/nht4UgKK8CoC4rP4ZQQFgGCUA3nNOGEUBKEzrB8yBuhSA4rwKgDis/hlJAWA4JQC+ci4YTQFgylOAYQe/zDgPnv5RAGitKQEwi/BnFgWAn5QAGEv4M5MCwHRKABW575lNAeCDWU8HhiGVzLrfPf1zTwHgCyUA+hH+RKEA8JASANcT/kSiABCOEsCK3NdEowDw1MynBsOSlcy8nz3984wCwEtKAJwj/IlKAeAtJQCOEf5EpgCwiRIA+wh/olMASEEJIBP3KxkoAGw2+6nCUCWD2ffp7HNKHt9+++P3v2b/EOQye8C1ZsgRj3NBNjYA7BZhyEQYtnAT4X6McC7JRQHgkAjDJsLQhQj3YYTzSD5eAXBKhOHXmgHIeO59srMB4JQowyfKMKaGKPdblPNHTgoAp0UZQlGGMmuLcp9FOXfk5RUAl4kyGFszHLme+5vV2ABwmUhDKdKwJr9I91Okc0ZuNgBcLtKwbM3A5Dj3MiuzAeBy0YZUtCFODtHum2jnivxsAOgm2gBtzRDlPfctVdgA0E3EoRVxuBNHxPsj4jliDTYAdBdxqLZmsPKLe5SKFACGiDpgWzNkK3NfUpkCwDCRh21rBm4l7kVQABgs+uBtzfBdmfsPflEAGC7DEG7NIF6Jew6+UgCYxlCmN/cYPKcAMFWWAd2aIZ2J+wreUwCYLtOwbs3Ajsy9BNspAISQbXDfGODzuXfgGAWAUAxztnKvwDkKAOFkHew3Bnw/7g24jgJASNkH/Y2Bf557AfpQAAhtleHfmgDYw+cO/SkAhLdSGNwIha98zjCWAkAKK4bDvYpB4TOFuRQAUlk9NO6tFCA+N4hHASCdSmHySOSA8dnE/WzgMwWAtKqHzTM9Q8g1f0zwk5ECQHpCiVkEP5l9n/0DwFmGMDO478jOBoCl2AbQm+BnFQoAS1IEuJrgZzUKAEtTBDhL8LMq3wFgaYY3Z7h/WJkNAGXYBrCV4KcCBYByFAGeEfxUogBQliLAjeCnIgUAmjJQkdCnOgUA7igC6xP88IMCAA8oAusR/PCRAgBvKAN5CX14TgGAjRSBPAQ/vKcAwAHKQDxCH/ZRAOAkZWAeoQ/HKQBwIWWgP6EP11AAoCOF4DyBD30oADCQQvCewIcxFACYSCEQ+DCLAgDBrFwKhD3EoQBAEpmKgaCH+BQAWMiIkiDcYQ3fWmtNCQCAOv787/++fZ/9QwAA4ykAAFCQAgAABSkAAFCQAgAABSkAAFCQAgAABX1v7cffA87+QQCA/m6ZbwMAAAUpAABQkAIAAAUpAABQ0M8C4IuAALC2+6y3AQCAghQAAChIAQCAgj4UAN8DAIA1fc54GwAAKEgBAICCFAAAKOhLAfA9AABYy6NstwEAgIIUAAAo6GEB8BoAANbwLNNtAACgIAUAAAp6WgC8BgCA3F5luQ0AABSkAABAQS8LgNcAAJDTuwy3AQCAgt4WAFsAAMhlS3bbAABAQQoAABS0qQB4DQAAOWzNbBsAAChocwGwBQCA2PZktQ0AABS0qwDYAgBATHsz2gYAAAraXQBsAQAgliPZbAMAAAUdKgC2AAAQw9FMtgEAgIIOFwBbAACY60wWn9oAKAEAMMfZDPYKAAAKOl0AbAEAYKwrstcGAAAKuqQA2AIAwBhXZe5lGwAlAAD6ujJrvQIAgIIuLQC2AADQx9UZe/kGQAkAgGv1yNYurwCUAAC4Rq9M9R0AACioWwGwBQCAc3pmadcNgBIAAMf0ztDurwCUAADYZ0R2+g4AABQ0pADYAgDANqMyc9gGQAkAgNdGZuXQVwBKAAA8Njojh38HQAkAgI9mZOOULwEqAQDww6xMnPZXAEoAANXNzMKpfwaoBABQ1ewMnP7vAMy+AAAwWoTsm14AWotxIQBghCiZF6IAtBbnggBAL5GyLkwBaC3WhQGAK0XLuFAFoLV4FwgAzoqYbeEKQGsxLxQAHBE100IWgNbiXjAA2CpyloUtAK3FvnAA8Er0DAtdAFqLfwEB4LMM2RX+B7z32x+//zX7ZwCAZzIE/034DcC9TBcWgFqyZVSqAtBavgsMwPoyZlO6H/ieVwIAzJQx+G/SbQDuZb7wAOSWPYNSF4DW8n8AAOSzQvak/wXueSUAQE8rBP9N+g3AvZU+GABiWS1jlvpl7tkGAHCF1YL/Zslf6p4iAMARqwb/zVKvAB5Z/QME4HoVsmP5X/CebQAAr1QI/psyv+g9RQCAe5WC/6bcL3xPEQCorWLw35T9xe8pAgC1VA7+m/IX4J4iALA2wf+LC/GEMgCwBqH/mIvyhiIAkJPgf83F2UEZAIhN6G/nQh2kDADEIPSPcdEuoAwAjCX0z3MBO1AIAK4l8K/ngg6gEADsI/D7c4EnUQoAfhD2c7joQSkIwCoEfEz/B1TR+BfwrSKmAAAAAElFTkSuQmCC''')
ICON_180 = base64.b64decode('''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''')

def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80)); ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(24)
app.permanent_session_lifetime = timedelta(days=180)
APP_PIN = os.environ.get('APP_PIN')   # se impostato, l'app chiede un PIN

def ensure_login():
    """Login automatico usando le variabili d'ambiente (per il cloud)."""
    if getattr(client, '_logged_in', False):
        return
    u, p = os.environ.get('XS_USER'), os.environ.get('XS_PASS')
    if u and p:
        client.login(u, p)

ALLOW_NO_PIN = {'index', 'manifest', 'icon192', 'icon512', 'appleicon',
                'sw', 'api_status', 'api_unlock'}

@app.before_request
def _gate():
    if not APP_PIN:
        return
    if request.endpoint in ALLOW_NO_PIN or request.endpoint is None:
        return
    if request.path.startswith('/api/') and not session.get('ok'):
        return jsonify({'locked': True}), 401


def monday_of(d): return d - dt.timedelta(days=d.weekday())
def parse_date(s):
    y, m, day = map(int, s.split("-")); return dt.date(y, m, day)


def catalog_to_json():
    catalog = client.get_catalog()
    out = []
    for c in catalog.values():
        if not c.projects:
            continue
        out.append({
            "id": c.id, "name": c.name,
            "projects": [
                {"id": p.id, "name": p.name,
                 "tasks": [{"id": t.id, "name": t.name} for t in p.tasks]}
                for p in c.projects
            ],
        })
    out.sort(key=lambda c: c["name"].lower())
    return out


def day_payload(d):
    entries = client.get_day_entries(d.year, d.month, d.day)
    total_min = 0
    for e in entries:
        try:
            h = int(e["total"].split("h")[0])
            m = int(e["total"].split("h")[1].replace("m", "").strip())
            total_min += h * 60 + m
        except Exception:
            pass
    return {"date": d.isoformat(), "weekday": d.weekday(),
            "entries": entries, "total_min": total_min}


@app.get("/api/status")
def api_status():
    try:
        ensure_login()
    except Exception:
        pass
    return jsonify({
        "needs_pin": bool(APP_PIN),
        "unlocked": (not APP_PIN) or bool(session.get("ok")),
        "username": getattr(client, "_user", ""),
    })


@app.post("/api/unlock")
def api_unlock():
    data = request.get_json(force=True)
    if APP_PIN and str(data.get("pin", "")) == str(APP_PIN):
        session.permanent = True
        session["ok"] = True
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 401


@app.get("/api/me")
def api_me():
    return jsonify({"username": getattr(client, "_user", "")})


@app.post("/api/login")
def api_login():
    data = request.get_json(force=True)
    try:
        client.login(data["username"], data["password"])
        return jsonify({"ok": True, "username": client._user})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.get("/api/catalog")
def api_catalog():
    ensure_login()
    return jsonify(catalog_to_json())


@app.get("/api/week")
def api_week():
    ensure_login()
    start = request.args.get("start")
    base = parse_date(start) if start else dt.date.today()
    mon = monday_of(base)
    days = [day_payload(mon + dt.timedelta(days=i)) for i in range(7)]
    return jsonify({"monday": mon.isoformat(), "days": days,
                    "week_total_min": sum(d["total_min"] for d in days)})


@app.post("/api/add")
def api_add():
    ensure_login()
    data = request.get_json(force=True)
    d = parse_date(data["date"])
    sh, sm = map(int, data["start"].split(":"))
    eh, em = map(int, data["end"].split(":"))
    sm = round(sm / 5) * 5 % 60
    em = round(em / 5) * 5 % 60
    client.add_entry(d.year, d.month, d.day,
                     data["client_id"], data["proj_id"], data["task_id"],
                     sh, sm, eh, em, log_message=data.get("note", ""))
    payload = day_payload(d)
    print(f"[add] {data['date']} -> {len(payload['entries'])} voci")
    return jsonify(payload)


@app.post("/api/delete")
def api_delete():
    ensure_login()
    data = request.get_json(force=True)
    d = parse_date(data["date"])
    client.delete_entry(d.year, d.month, d.day, data["trans_num"])
    return jsonify(day_payload(d))



@app.get("/manifest.webmanifest")
def manifest():
    data = {
        "name": "Le mie ore", "short_name": "Ore", "display": "standalone",
        "background_color": "#0d1211", "theme_color": "#0d1211",
        "start_url": "/", "scope": "/", "orientation": "portrait-primary",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ],
    }
    return jsonify(data)


@app.get("/icon-192.png")
def icon192():
    return Response(ICON_192, mimetype="image/png")


@app.get("/icon-512.png")
def icon512():
    return Response(ICON_512, mimetype="image/png")


@app.get("/apple-touch-icon.png")
@app.get("/apple-touch-icon-precomposed.png")
def appleicon():
    return Response(ICON_180, mimetype="image/png")


@app.get("/sw.js")
def sw():
    js = "self.addEventListener('fetch', e => {});"
    return Response(js, mimetype="application/javascript")


@app.get("/")
def index():
    return Response(PAGE, mimetype="text/html")


PAGE = r"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<script>document.documentElement.dataset.theme=localStorage.getItem("xs-theme")||"dark";</script>
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Le mie ore</title>
<meta name="theme-color" content="#0d1211">
<link rel="manifest" href="/manifest.webmanifest">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Le mie ore">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,500;9..144,600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#0d1211; --panel:#141c1a; --ink:#f2ede1; --ink-dim:#cfc9bb;
  --muted:#8b938c; --faint:#5f665f;
  --line:rgba(208,190,150,.12); --line-strong:rgba(208,190,150,.22);
  --gold:#c9ad74; --gold-deep:#a8884f; --emerald:#62b89a; --danger:#cf8076;
  --on-gold:#1a140a; --input-bg:#0f1715;
  --block-bg:linear-gradient(180deg,#16201e,#131b19); --block-weekend-bg:#0f1715;
  --page-bg:
    radial-gradient(1200px 600px at 78% -8%, rgba(201,173,116,.10), transparent 60%),
    radial-gradient(900px 500px at 10% 8%, rgba(98,184,154,.06), transparent 55%), #0d1211;
  --r:18px; --r-sm:12px;
  --shadow:0 24px 60px -28px rgba(0,0,0,.7), 0 2px 8px -2px rgba(0,0,0,.4);
}
html[data-theme="light"]{
  --bg:#f3efe6; --panel:#fbf9f4; --ink:#1d2422; --ink-dim:#3f4a45;
  --muted:#7c837d; --faint:#a7ada6;
  --line:rgba(40,34,18,.10); --line-strong:rgba(40,34,18,.18);
  --gold:#9a7b3f; --gold-deep:#7d6230; --emerald:#2f8c6e; --danger:#b4554a;
  --on-gold:#fffaf0; --input-bg:#fbf9f4;
  --block-bg:linear-gradient(180deg,#ffffff,#faf7f0); --block-weekend-bg:#efeadd;
  --page-bg:
    radial-gradient(1200px 600px at 80% -10%, rgba(154,123,63,.10), transparent 60%),
    radial-gradient(900px 500px at 8% 6%, rgba(47,140,110,.07), transparent 55%), #f3efe6;
  --shadow:0 22px 54px -30px rgba(70,58,30,.45), 0 2px 8px -4px rgba(0,0,0,.10);
}
*{box-sizing:border-box}
html,body{margin:0; background:var(--bg); color:var(--ink);
  font-family:Inter,system-ui,sans-serif; -webkit-font-smoothing:antialiased; line-height:1.5}
body{min-height:100vh; background:var(--page-bg); transition:background .3s,color .3s}
.serif{font-family:Fraunces,Georgia,serif}
.eyebrow{font-size:11px; letter-spacing:.22em; text-transform:uppercase; color:var(--muted); font-weight:500}
.tnum{font-variant-numeric:tabular-nums}
button{font:inherit; cursor:pointer; border:none; background:none; color:inherit}
.wrap{max-width:1140px; margin:0 auto; padding:40px 28px 100px}

.top{display:flex; align-items:flex-end; gap:24px; flex-wrap:wrap}
.brand .eyebrow{margin-bottom:6px}
.brand h1{font-weight:400; font-size:40px; line-height:1; margin:0; letter-spacing:-.01em}
.brand h1 em{font-style:italic; color:var(--gold)}
.spacer{flex:1}
.icon-btn{width:44px; height:44px; border-radius:50%; border:1px solid var(--line-strong);
  display:grid; place-items:center; color:var(--ink-dim); transition:.2s}
.icon-btn:hover{border-color:var(--gold); color:var(--gold)}
.icon-btn svg{width:20px; height:20px}
.rule{height:1px; background:linear-gradient(90deg,var(--gold-deep),transparent 70%); opacity:.5; margin:22px 0 26px}

.weekbar{display:flex; align-items:center; gap:18px; flex-wrap:wrap; margin-bottom:26px}
.nav{display:flex; align-items:center; gap:8px}
.nav .arrow{width:40px; height:40px; border-radius:50%; border:1px solid var(--line);
  color:var(--ink-dim); display:grid; place-items:center; transition:.2s}
.nav .arrow:hover{border-color:var(--gold); color:var(--gold)}
.nav .now{padding:0 18px; height:40px; border-radius:999px; border:1px solid var(--line);
  color:var(--ink-dim); font-size:13px; transition:.2s}
.nav .now:hover{border-color:var(--gold); color:var(--gold)}
.range{font-size:15px; color:var(--ink-dim)}
.range .serif{font-size:17px}
.wtotal{margin-left:auto; text-align:right}
.wtotal .eyebrow{margin-bottom:2px}
.wtotal .v{font-family:Fraunces,serif; font-size:30px; line-height:1; color:var(--gold)}
.wtotal .v small{font-size:15px; color:var(--muted); font-family:Inter}

.grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(134px,1fr)); gap:14px}
.block{position:relative; background:var(--block-bg); border:1px solid var(--line);
  border-radius:var(--r); padding:18px 16px 16px; min-height:158px; display:flex; flex-direction:column;
  cursor:pointer; transition:transform .18s,border-color .18s,box-shadow .18s; overflow:hidden}
.block:hover{transform:translateY(-3px); border-color:var(--line-strong); box-shadow:var(--shadow)}
.block .wd{font-size:11px; letter-spacing:.16em; text-transform:uppercase; color:var(--muted)}
.block .dnum{font-family:Fraunces,serif; font-weight:300; font-size:46px; line-height:.95; margin-top:2px}
.block .filler{flex:1}
.block .total{font-family:Fraunces,serif; font-size:22px; color:var(--gold); line-height:1}
.block .total.zero{color:var(--faint); font-size:18px; font-style:italic; font-weight:300}
.block .count{font-size:12px; color:var(--muted); margin-top:4px}
.block .dots{display:flex; gap:5px; margin-top:10px}
.block .dot{width:6px; height:6px; border-radius:50%; background:var(--gold-deep); opacity:.85}
.block.weekend{background:var(--block-weekend-bg)}
.block.weekend .dnum{color:var(--ink-dim)}
.block.today{border-color:var(--gold)}
.block.today::after{content:""; position:absolute; inset:0; border-radius:var(--r);
  box-shadow:inset 0 0 0 1px var(--gold), 0 0 40px -10px rgba(201,173,116,.4); pointer-events:none}
.block .badge{position:absolute; top:14px; right:14px; font-size:9px; letter-spacing:.18em;
  text-transform:uppercase; color:var(--gold); border:1px solid var(--gold-deep); border-radius:999px; padding:3px 7px}

.summary{margin-top:34px; display:none}
.summary.show{display:block}
.summary-head{display:flex; align-items:center; gap:12px; margin-bottom:16px}
.summary-head .l{flex:1; height:1px; background:var(--line)}
.sum-grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px}
.sum-card{border:1px solid var(--line); border-radius:var(--r-sm); padding:16px 18px; background:var(--panel)}
.sum-card .cname{font-size:14px; color:var(--ink); margin-bottom:10px; display:flex; align-items:center; gap:8px}
.sum-card .cname .pip{width:8px; height:8px; border-radius:50%; background:var(--gold)}
.sum-card .bar{height:6px; border-radius:999px; background:var(--line); overflow:hidden; margin-bottom:8px}
.sum-card .bar i{display:block; height:100%; background:linear-gradient(90deg,var(--gold),var(--gold-deep))}
.sum-card .ch{font-family:Fraunces,serif; font-size:20px; color:var(--gold)}
.sum-stats{display:flex; gap:26px; margin-top:18px; flex-wrap:wrap}
.sum-stats .stat .eyebrow{margin-bottom:4px}
.sum-stats .stat .sv{font-family:Fraunces,serif; font-size:24px; color:var(--ink)}

.overlay{position:fixed; inset:0; background:rgba(6,9,8,.6); backdrop-filter:blur(6px);
  display:none; align-items:center; justify-content:center; padding:24px; z-index:50}
html[data-theme="light"] .overlay{background:rgba(60,52,32,.32)}
.overlay.open{display:flex}
.sheet{width:100%; max-width:540px; max-height:88vh; overflow:auto; background:var(--panel);
  border:1px solid var(--line-strong); border-radius:24px; box-shadow:var(--shadow)}
.sheet-head{display:flex; align-items:flex-start; gap:14px; padding:26px 28px 18px;
  border-bottom:1px solid var(--line); position:sticky; top:0; background:var(--panel); z-index:2}
.sheet-head .eyebrow{margin-bottom:6px}
.sheet-head h2{margin:0; font-weight:400; font-size:26px; line-height:1.1; text-transform:capitalize}
.sheet-head .close{margin-left:auto; width:38px; height:38px; border-radius:50%; border:1px solid var(--line);
  color:var(--muted); display:grid; place-items:center; transition:.2s; flex:none}
.sheet-head .close:hover{border-color:var(--danger); color:var(--danger)}
.sheet-body{padding:22px 28px 28px}

.entry{display:flex; align-items:center; gap:14px; padding:14px 16px; border-radius:var(--r-sm);
  border:1px solid var(--line); margin-bottom:10px}
.entry .tline{font-family:Fraunces,serif; font-size:18px; white-space:nowrap}
.entry .meta{min-width:0}
.entry .meta .desc{font-size:12.5px; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap}
.entry .dur{margin-left:auto; font-size:13px; color:var(--gold)}
.entry .del{width:30px; height:30px; border-radius:50%; border:1px solid var(--line); color:var(--muted);
  display:grid; place-items:center; flex:none; transition:.2s}
.entry .del:hover{border-color:var(--danger); color:var(--danger)}
.empty{padding:18px 4px; color:var(--faint); font-style:italic; font-size:14px}

.section-label{display:flex; align-items:center; gap:12px; margin:26px 0 14px}
.section-label .eyebrow{white-space:nowrap}
.section-label .l{flex:1; height:1px; background:var(--line)}
.field{margin-bottom:12px}
.field label{display:block; font-size:11px; letter-spacing:.1em; text-transform:uppercase; color:var(--muted); margin-bottom:6px}
select,input[type=time],textarea,input[type=text],input[type=password]{
  width:100%; padding:12px 13px; background:var(--input-bg); border:1px solid var(--line-strong);
  border-radius:var(--r-sm); color:var(--ink); font:inherit; transition:border-color .2s}
select:focus,input:focus,textarea:focus{outline:none; border-color:var(--gold)}
select:disabled{opacity:.4}
textarea{resize:vertical}
.row2{display:flex; gap:12px}
.row2>div{flex:1}
.actions{display:flex; gap:10px; margin-top:20px}
.btn{padding:13px 22px; border-radius:999px; font-weight:500; font-size:14px; transition:.2s}
.btn-gold{background:linear-gradient(180deg,var(--gold),var(--gold-deep)); color:var(--on-gold); font-weight:600}
.btn-gold:hover{filter:brightness(1.06)}
.btn-gold:disabled{opacity:.4; cursor:not-allowed; filter:none}
.btn-ghost{border:1px solid var(--line); color:var(--muted)}
.btn-ghost:hover{border-color:var(--ink-dim); color:var(--ink-dim)}
.hint{font-size:12px; color:var(--faint); margin-top:8px}
.warn{font-size:12.5px; color:var(--danger); margin-top:8px; display:none}
.warn.show{display:block}

.seg{display:inline-flex; border:1px solid var(--line-strong); border-radius:999px; padding:4px; gap:4px}
.seg button{padding:8px 18px; border-radius:999px; font-size:13px; color:var(--muted); transition:.2s}
.seg button.active{background:linear-gradient(180deg,var(--gold),var(--gold-deep)); color:var(--on-gold); font-weight:600}

.toast{position:fixed; left:50%; bottom:30px; transform:translate(-50%,12px); opacity:0;
  background:var(--panel); border:1px solid var(--gold-deep); color:var(--ink); padding:13px 22px;
  border-radius:999px; font-size:14px; transition:.25s; pointer-events:none; z-index:60; box-shadow:var(--shadow)}
.toast.show{opacity:1; transform:translate(-50%,0)}
.loading{grid-column:1/-1; text-align:center; color:var(--muted); padding:60px 0; font-style:italic}

@media(max-width:560px){
  .wrap{padding:28px 18px 90px}
  .brand h1{font-size:32px}
  .wtotal{margin-left:0; width:100%; text-align:left}
}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div class="brand"><div class="eyebrow">Timesheet</div><h1 class="serif">Le mie <em>ore</em></h1></div>
    <div class="spacer"></div>
    <button class="icon-btn" id="open-settings" title="Impostazioni">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
    </button>
  </div>
  <div class="rule"></div>

  <div class="weekbar">
    <div class="nav">
      <button class="arrow" id="prev" title="Settimana precedente (←)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg></button>
      <button class="now" id="now">Questa settimana</button>
      <button class="arrow" id="next" title="Settimana successiva (→)"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg></button>
    </div>
    <div class="range" id="range"></div>
    <div class="wtotal"><div class="eyebrow">Totale settimana</div><div class="v" id="wtotal">—</div></div>
  </div>

  <div class="grid" id="grid"><div class="loading">Carico la settimana…</div></div>

  <div class="summary" id="summary">
    <div class="summary-head"><span class="eyebrow">Riepilogo settimana</span><span class="l"></span></div>
    <div class="sum-grid" id="sum-grid"></div>
    <div class="sum-stats" id="sum-stats"></div>
  </div>
</div>

<div class="overlay" id="day-overlay">
  <div class="sheet">
    <div class="sheet-head">
      <div><div class="eyebrow" id="day-eyebrow">Giornata</div><h2 class="serif" id="day-title"></h2></div>
      <button class="close" data-close="day"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
    </div>
    <div class="sheet-body" id="day-body"></div>
  </div>
</div>

<div class="overlay" id="set-overlay">
  <div class="sheet">
    <div class="sheet-head">
      <div><div class="eyebrow">Account</div><h2 class="serif">Impostazioni</h2></div>
      <button class="close" data-close="set"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
    </div>
    <div class="sheet-body">
      <div class="section-label"><span class="eyebrow">Aspetto</span><span class="l"></span></div>
      <div class="field"><label>Tema</label>
        <div class="seg" id="theme-seg">
          <button data-theme="dark">Scuro</button>
          <button data-theme="light">Chiaro</button>
        </div>
      </div>

      <div class="section-label"><span class="eyebrow">Utente collegato</span><span class="l"></span></div>
      <div class="field"><label>Username</label><input type="text" id="set-username" autocomplete="username"></div>
      <div class="field"><label>Password</label><input type="password" id="set-password" placeholder="•••••••• (per cambiare utente)" autocomplete="current-password"></div>
      <button class="btn btn-ghost" id="relogin">Accedi con questo utente</button>
      <p class="hint">Le credenziali restano solo in memoria sul tuo PC finché il programma è in esecuzione.</p>
    </div>
  </div>
</div>

<div class="overlay" id="pin-overlay">
  <div class="sheet" style="max-width:380px">
    <div class="sheet-head"><div><div class="eyebrow">Accesso</div><h2 class="serif">Sblocca</h2></div></div>
    <div class="sheet-body">
      <div class="field"><label>PIN</label><input type="password" id="pin-input" inputmode="numeric" placeholder="••••" autocomplete="off"></div>
      <div class="warn" id="pin-warn">PIN errato, riprova.</div>
      <div class="actions"><button class="btn btn-gold" id="pin-go" style="width:100%">Entra</button></div>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const WD_LONG=["lunedì","martedì","mercoledì","giovedì","venerdì","sabato","domenica"];
const WD_SHORT=["lun","mar","mer","gio","ven","sab","dom"];
let catalog=[], monday=null, currentDays=[];

function fmtMin(m){const h=Math.floor(m/60),r=m%60;return h+"h"+(r?" "+(r<10?"0":"")+r+"m":"");}
function entryMin(e){try{const h=parseInt(e.total.split("h")[0]||0);const m=parseInt((e.total.split("h")[1]||"").replace("m","").trim()||0);return h*60+m;}catch(_){return 0;}}
function toast(msg){const t=document.getElementById("toast");t.textContent=msg;t.classList.add("show");clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove("show"),2300);}
const todayISO=()=>new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,10);

async function loadCatalog(){catalog=await(await fetch("/api/catalog")).json();}
async function loadMe(){const me=await(await fetch("/api/me")).json();document.getElementById("set-username").value=me.username||"";}

async function loadWeek(start){
  document.getElementById("grid").innerHTML='<div class="loading">Carico la settimana…</div>';
  const data=await(await fetch(start?"/api/week?start="+start:"/api/week")).json();
  monday=data.monday; currentDays=data.days; renderWeek(data);
}

function renderWeek(data){
  const m=new Date(data.monday+"T00:00"),end=new Date(m);end.setDate(end.getDate()+6);
  const o={day:"numeric",month:"long"};
  document.getElementById("range").innerHTML=
    '<span class="serif">'+m.toLocaleDateString("it-IT",o)+'</span> — <span class="serif">'+end.toLocaleDateString("it-IT",o)+'</span>';
  document.getElementById("wtotal").innerHTML=data.week_total_min?fmtMin(data.week_total_min):'<small>nessuna ora</small>';

  const tISO=todayISO(); const grid=document.getElementById("grid"); grid.innerHTML="";
  data.days.forEach((day,i)=>{
    const weekend=day.weekday>=5, today=day.date===tISO;
    const el=document.createElement("div");
    el.className="block"+(weekend?" weekend":"")+(today?" today":"");
    const dots=day.entries.slice(0,5).map(()=>'<span class="dot"></span>').join("");
    el.innerHTML=`${today?'<span class="badge">oggi</span>':''}
      <div class="wd">${WD_SHORT[day.weekday]}</div>
      <div class="dnum tnum">${day.date.slice(8,10)}</div>
      <div class="filler"></div>
      ${day.total_min
        ? `<div class="total tnum">${fmtMin(day.total_min)}</div>
           <div class="count">${day.entries.length} ${day.entries.length===1?'voce':'voci'}</div>
           <div class="dots">${dots}</div>`
        : `<div class="total zero">libero</div>`}`;
    el.onclick=()=>openDay(i);
    grid.appendChild(el);
  });
  renderSummary(data);
}

function renderSummary(data){
  const box=document.getElementById("summary");
  if(!data.week_total_min){box.classList.remove("show");return;}
  box.classList.add("show");
  const byClient={};
  data.days.forEach(d=>d.entries.forEach(e=>{byClient[e.client]=(byClient[e.client]||0)+entryMin(e);}));
  const max=Math.max(...Object.values(byClient));
  const rows=Object.entries(byClient).sort((a,b)=>b[1]-a[1]);
  document.getElementById("sum-grid").innerHTML=rows.map(([name,min])=>`
    <div class="sum-card">
      <div class="cname"><span class="pip"></span>${name}</div>
      <div class="bar"><i style="width:${Math.round(min/max*100)}%"></i></div>
      <div class="ch tnum">${fmtMin(min)}</div>
    </div>`).join("");
  const worked=data.days.filter(d=>d.total_min>0).length;
  const avg=worked?Math.round(data.week_total_min/worked):0;
  document.getElementById("sum-stats").innerHTML=`
    <div class="stat"><div class="eyebrow">Giorni lavorati</div><div class="sv tnum">${worked}</div></div>
    <div class="stat"><div class="eyebrow">Media al giorno</div><div class="sv tnum">${fmtMin(avg)}</div></div>
    <div class="stat"><div class="eyebrow">Clienti</div><div class="sv tnum">${rows.length}</div></div>`;
}

/* ---------- DAY ---------- */
function openDay(i){
  const day=currentDays[i], d=new Date(day.date+"T00:00");
  document.getElementById("day-eyebrow").textContent=day.total_min?("Totale "+fmtMin(day.total_min)):"Giornata libera";
  document.getElementById("day-title").textContent=WD_LONG[day.weekday]+" "+d.toLocaleDateString("it-IT",{day:"numeric",month:"long"});
  renderDayBody(i); show("day");
}

function renderDayBody(i){
  const day=currentDays[i], body=document.getElementById("day-body"); body.innerHTML="";
  if(!day.entries.length){
    body.insertAdjacentHTML("beforeend",'<div class="empty">Nessuna ora registrata in questa giornata.</div>');
  }else{
    day.entries.forEach(e=>{
      const row=document.createElement("div"); row.className="entry";
      row.innerHTML=`
        <div class="tline tnum">${e.start}<span style="color:var(--faint)"> – </span>${e.end}</div>
        <div class="meta"><div class="desc" style="color:var(--ink)">${e.client} · ${e.project}</div>
          <div class="desc">${e.task||''}</div></div>
        <div class="dur tnum">${e.total}</div>
        <button class="del" title="Elimina">${e.trans_num?'<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>':'·'}</button>`;
      const del=row.querySelector(".del");
      if(e.trans_num){del.onclick=()=>deleteEntry(i,day.date,e.trans_num);}else{del.disabled=true;}
      body.appendChild(row);
    });
  }
  body.insertAdjacentHTML("beforeend",`
    <div class="section-label"><span class="eyebrow">Aggiungi ore</span><span class="l"></span></div>
    <div class="field"><label>Cliente</label><select class="f-client"><option value="">— seleziona —</option></select></div>
    <div class="field"><label>Progetto</label><select class="f-proj" disabled><option value="">—</option></select></div>
    <div class="field"><label>Task</label><select class="f-task" disabled><option value="">—</option></select></div>
    <div class="row2">
      <div class="field"><label>Inizio</label><input type="time" class="f-start" step="300" value="10:00"></div>
      <div class="field"><label>Fine</label><input type="time" class="f-end" step="300" value="18:00"></div>
    </div>
    <div class="field"><label>Note (facoltative)</label><textarea class="f-note" rows="2" placeholder="Annotazioni per questa registrazione…"></textarea></div>
    <div class="warn" id="warn-${i}">La fine deve essere successiva all'inizio.</div>
    <div class="actions"><button class="btn btn-gold f-save" disabled>Salva le ore</button></div>`);
  wireAddForm(i, day.date, body);
}

function wireAddForm(i, date, body){
  const cSel=body.querySelector(".f-client"), pSel=body.querySelector(".f-proj"),
        tSel=body.querySelector(".f-task"), save=body.querySelector(".f-save"),
        sIn=body.querySelector(".f-start"), eIn=body.querySelector(".f-end"),
        warn=body.querySelector(".warn");
  catalog.forEach(c=>cSel.add(new Option(c.name,c.id)));
  const validTime=()=>eIn.value>sIn.value;
  const upd=()=>{
    const ok=cSel.value&&pSel.value&&tSel.value;
    const t=validTime(); warn.classList.toggle("show",!t&&!!(sIn.value&&eIn.value));
    save.disabled=!(ok&&t);
  };
  cSel.onchange=()=>{
    pSel.innerHTML='<option value="">— seleziona —</option>'; pSel.disabled=true;
    tSel.innerHTML='<option value="">—</option>'; tSel.disabled=true;
    const c=catalog.find(x=>x.id===cSel.value);
    if(c){c.projects.forEach(p=>pSel.add(new Option(p.name,p.id)));pSel.disabled=false;}
    upd();
  };
  pSel.onchange=()=>{
    tSel.innerHTML='<option value="">— seleziona —</option>'; tSel.disabled=true;
    const c=catalog.find(x=>x.id===cSel.value), p=c&&c.projects.find(x=>x.id===pSel.value);
    if(p){p.tasks.forEach(t=>tSel.add(new Option(t.name,t.id)));tSel.disabled=false;if(p.tasks.length===1)tSel.value=p.tasks[0].id;}
    upd();
  };
  tSel.onchange=upd; sIn.oninput=upd; eIn.oninput=upd;
  save.onclick=async()=>{
    save.disabled=true; save.textContent="Salvo…";
    const b={date,client_id:cSel.value,proj_id:pSel.value,task_id:tSel.value,
             start:sIn.value,end:eIn.value,note:body.querySelector(".f-note").value};
    try{
      const r=await fetch("/api/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});
      if(!r.ok)throw 0;
      currentDays[i]=await r.json(); toast("Ore salvate"); renderDayBody(i); refreshGridSilently();
    }catch(e){toast("Errore nel salvataggio"); save.disabled=false; save.textContent="Salva le ore";}
  };
}

async function deleteEntry(i,date,trans_num){
  if(!confirm("Eliminare questa registrazione?"))return;
  try{
    const r=await fetch("/api/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({date,trans_num})});
    if(!r.ok)throw 0;
    currentDays[i]=await r.json(); toast("Registrazione eliminata"); renderDayBody(i); refreshGridSilently();
  }catch(e){toast("Errore nell'eliminazione");}
}

async function refreshGridSilently(){
  const data=await(await fetch("/api/week?start="+monday)).json();
  currentDays=data.days; renderWeek(data);
}

/* ---------- overlays ---------- */
function show(w){document.getElementById(w+"-overlay").classList.add("open");}
function hide(w){document.getElementById(w+"-overlay").classList.remove("open");}
document.querySelectorAll("[data-close]").forEach(b=>b.onclick=()=>hide(b.dataset.close));
document.querySelectorAll(".overlay").forEach(o=>o.onclick=e=>{if(o.id!=="pin-overlay"&&e.target===o)o.classList.remove("open");});

/* ---------- theme ---------- */
function setTheme(t){
  document.documentElement.dataset.theme=t; localStorage.setItem("xs-theme",t);
  document.querySelectorAll("#theme-seg button").forEach(b=>b.classList.toggle("active",b.dataset.theme===t));
}
document.querySelectorAll("#theme-seg button").forEach(b=>b.onclick=()=>setTheme(b.dataset.theme));
setTheme(localStorage.getItem("xs-theme")||"dark");

/* ---------- settings ---------- */
document.getElementById("open-settings").onclick=()=>show("set");
document.getElementById("relogin").onclick=async()=>{
  const u=document.getElementById("set-username").value, p=document.getElementById("set-password").value;
  if(!u||!p){toast("Inserisci username e password");return;}
  const r=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username:u,password:p})});
  if(r.ok){toast("Accesso aggiornato");document.getElementById("set-password").value="";hide("set");await loadCatalog();await loadWeek(monday);}
  else{toast("Login fallito");}
};

/* ---------- nav + tastiera ---------- */
function shift(days){const m=new Date(monday+"T00:00");m.setDate(m.getDate()+days);loadWeek(m.toISOString().slice(0,10));}
document.getElementById("prev").onclick=()=>shift(-7);
document.getElementById("next").onclick=()=>shift(7);
document.getElementById("now").onclick=()=>loadWeek(null);
document.addEventListener("keydown",e=>{
  if(e.key==="Escape"){document.querySelectorAll(".overlay.open").forEach(o=>{if(o.id!=="pin-overlay")o.classList.remove("open");});return;}
  if(document.querySelector(".overlay.open"))return;
  if(/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName))return;
  if(e.key==="ArrowLeft")shift(-7);
  if(e.key==="ArrowRight")shift(7);
});

if('serviceWorker' in navigator){try{navigator.serviceWorker.register('/sw.js').catch(()=>{});}catch(e){}}
async function start(){await loadMe();await loadCatalog();await loadWeek(null);}
function showPin(){document.getElementById('pin-overlay').classList.add('open');setTimeout(()=>document.getElementById('pin-input').focus(),50);}
async function unlock(){const pin=document.getElementById('pin-input').value;const r=await fetch('/api/unlock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin})});if(r.ok){document.getElementById('pin-overlay').classList.remove('open');await start();}else{document.getElementById('pin-warn').classList.add('show');}}
document.getElementById('pin-go').onclick=unlock;
document.getElementById('pin-input').addEventListener('keydown',e=>{if(e.key==='Enter')unlock();});
(async()=>{const st=await(await fetch('/api/status')).json();if(st.needs_pin&&!st.unlocked){showPin();}else{await start();}})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    if os.environ.get("XS_USER") and os.environ.get("XS_PASS"):
        client.login(os.environ["XS_USER"], os.environ["XS_PASS"])
    else:
        u, pwd = _get_credentials(); client.login(u, pwd)
    port = int(os.environ.get("PORT", "5000"))
    ip = lan_ip()
    print("Login OK.\n")
    print(f"  Sul PC:        http://127.0.0.1:{port}")
    print(f"  Sul telefono:  http://{ip}:{port}   (stessa rete Wi-Fi)\n")
    app.run(host="0.0.0.0", port=port, debug=False)
