"""Répliques de repli (règles rapides et mode démonstration) — sans LLM."""
from systems.relationships import text_sentiment

GREET = ["Bonjour {t} !", "Salut {t}, comment ça va ?", "Oh, bonjour {t}. On ne s'est pas beaucoup parlé, non ?",
         "Hé {t} ! Belle journée, n'est-ce pas ?", "Bonsoir {t}."]
SMALL = ["Tu fais quoi de beau à {place} ?", "Je cherche un moyen de gagner un peu d'argent. Une idée ?",
         "Tu as lu les nouveautés sur IACHAT ?", "J'aimerais bien fabriquer quelque chose et le vendre.",
         "Il y a beaucoup de monde par ici aujourd'hui.", "Tu connais de bons endroits en ville ?",
         "Je me demande ce qu'on pourrait organiser entre habitants."]
POS = ["Content de te l'entendre dire, {t} !", "Oui, tout à fait, {t}.", "Ah, intéressant ! Raconte-m'en plus.",
       "Merci {t}, ça me fait plaisir.", "Bonne idée, on devrait s'y mettre ensemble."]
NEU = ["Hum, je vois.", "Je ne sais pas trop, {t}.", "Peut-être. Je vais y réfléchir.", "D'accord, {t}.", "Ah bon ? Je n'étais pas au courant."]
NEG = ["Je n'aime pas ce ton, {t}.", "Calme-toi, s'il te plaît.", "Je ne te fais plus confiance comme avant, {t}.", "On n'a rien à se dire."]
BYE = ["À plus tard, {t} !", "Bon, je dois y aller. Salut !", "Je te laisse, {t}. Bonne journée !"]
AD = ["Fait maison : « {item} », seulement {price} pièces. Venez voir !", "Je vends « {item} » à {price}. Qui est intéressé ?"]
SMS_REPLY = ["Merci pour ton message, {t} !", "Bien reçu, {t}. On se voit bientôt ?", "Je suis occupé(e) mais je t'écris plus tard."]


BYE_MARKERS = ("à plus tard", "je te laisse", "bon, je dois y aller", "au revoir", "bonne journée")


def is_goodbye(text):
    low = (text or "").lower()
    return any(m in low for m in BYE_MARKERS)


def pick(rng, items, **kw):
    return rng.choice(items).format(**kw)


def reply_line(rng, speaker_name, heard_text, trust=0.3, hostility=0.0, turns=0):
    """Renvoie (texte, ton, fin_de_conversation)."""
    tone = text_sentiment(heard_text)
    t = speaker_name
    if hostility > 0.5 or tone < 0:
        return pick(rng, NEG, t=t), -0.5, True
    if turns >= 5 and rng.random() < 0.5 or rng.random() < 0.12:
        return pick(rng, BYE, t=t), 0.3, True
    if "?" in heard_text and rng.random() < 0.6:
        return pick(rng, NEU, t=t), 0.0, False
    if tone > 0 or trust > 0.4:
        return pick(rng, POS, t=t), 0.5, False
    return pick(rng, NEU + SMALL[:3], t=t, place="ici"), 0.1, False
