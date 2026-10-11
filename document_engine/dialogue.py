"""Dialogue CLI : pose les questions manquantes, retourne data complete.

Regles strictes :
- Un champ obligatoire SANS reponse utilisateur -> on repose la question.
- On n'utilise JAMAIS un exemple comme valeur par defaut.
- Si lignes est obligatoire et vide apres saisie -> refus de generer.
"""
from __future__ import annotations
from .fields import load_fields, champs_manquants, appliquer_defauts


def _ask(question, defaut=None, obligatoire=False, exemple=None):
    """Pose une question.
    - Si obligatoire : on n'accepte pas une reponse vide.
    - L'exemple n'est PAS un defaut : il est juste affiche comme indice.
    """
    prompt = f"  {question}"
    if defaut:
        prompt += f" [{defaut}]"
    if exemple and not defaut:
        prompt += f" (ex. : {exemple})"
    prompt += " : "

    for tentative in range(5):
        try:
            rep = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            raise KeyboardInterrupt

        if rep:
            return rep
        if defaut:
            return str(defaut)
        if obligatoire:
            print("      [!] Ce champ est obligatoire, merci de saisir une valeur.")
            continue
        return ""  # optionnel vide = accepte
    raise KeyboardInterrupt("Trop de tentatives vides")


def _ask_lignes(sous_champs):
    """Saisie des lignes. Refuse de terminer tant qu'aucune ligne n'a ete saisie."""
    lignes = []
    print()
    print("  --- Saisie des lignes ---")
    print("  Saisissez au moins UNE ligne.")
    print("  Apres chaque ligne, tapez 'fin' a la description pour terminer.")
    while True:
        print(f"\n  Ligne {len(lignes) + 1} :")
        if lignes:
            description = input("  Description (ou 'fin' pour terminer) : ").strip()
            if description.lower() in ("fin", "stop", "q"):
                break
        else:
            # Premiere ligne : description obligatoire
            description = _ask("Description", obligatoire=True)

        if not description:
            print("      [!] Description obligatoire.")
            continue

        ligne = {"description": description}

        qte = _ask("Quantite", defaut="1")
        try:
            ligne["quantite"] = int(qte)
        except ValueError:
            ligne["quantite"] = 1

        prix = _ask("Prix unitaire HT", obligatoire=True)
        try:
            ligne["prix_ht"] = float(prix.replace(",", "."))
        except ValueError:
            print("      [!] Prix invalide, valeur 0 appliquee.")
            ligne["prix_ht"] = 0.0

        tva = _ask("Taux TVA %", defaut=sous_champs.get("tva_pct", {}).get("defaut", "20"))
        ligne["tva_pct"] = tva
        lignes.append(ligne)

    return lignes


def collecter_donnees(template_dir, data_initial=None):
    """Dialogue complet. Refuse de retourner tant que les obligatoires ne sont pas remplis."""
    fields = load_fields(template_dir)
    data = dict(data_initial or {})

    # 1. Appliquer les defauts pour les OPTIONNELS uniquement
    data = appliquer_defauts(fields, data)

    # 2. Poser les questions pour les obligatoires manquants
    manquants = champs_manquants(fields, data)

    if manquants:
        print()
        print("=" * 60)
        print(" INFORMATIONS REQUISES")
        print("=" * 60)
        print(f"  {len(manquants)} champ(s) obligatoire(s) manquant(s).")

    for m in manquants:
        chemin = m["chemin"]
        if chemin == "lignes" and m.get("sous_champs"):
            while True:
                data["lignes"] = _ask_lignes(m["sous_champs"])
                if data["lignes"]:
                    break
                print("      [!] Au moins une ligne est requise.")
            continue
        # Champ obligatoire : pas de defaut, on insiste
        rep = _ask(m["question"], defaut=None, obligatoire=True,
                    exemple=m.get("exemple"))
        if rep:
            parts = chemin.split(".")
            cur = data
            for p in parts[:-1]:
                cur = cur.setdefault(p, {})
            cur[parts[-1]] = rep

    # 3. Re-appliquer les defauts restants (pour les optionnels)
    data = appliquer_defauts(fields, data)

    # 4. RE-VERIFICATION : aucune tolerance sur les obligatoires
    restants = champs_manquants(fields, data)
    if restants:
        noms = ", ".join(r["chemin"] for r in restants)
        raise ValueError(f"Champs obligatoires toujours vides : {noms}")

    return data


def afficher_resume(data, fields):
    """Affiche un resume avant generation."""
    print()
    print("=" * 60)
    print(" RESUME")
    print("=" * 60)
    for chemin in fields.get("champs", {}):
        if chemin == "lignes":
            continue
        parts = chemin.split(".")
        cur = data
        ok = True
        for p in parts:
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                ok = False
                break
        if ok and cur:
            print(f"  {chemin:25s} : {cur}")
    lignes = data.get("lignes", [])
    if lignes:
        print(f"  lignes ({len(lignes)}) :")
        for l in lignes:
            print(f"    - {l.get('description', '')}  "
                  f"{l.get('quantite', '')} x {l.get('prix_ht', '')} EUR  "
                  f"TVA {l.get('tva_pct', '20')}%")
    else:
        print("  lignes : AUCUNE -> impossible de generer")
        return False
    print("=" * 60)
    return True


def confirmer():
    try:
        rep = input("\nGenerer le document ? [O/n] : ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return rep in ("", "o", "oui", "y", "yes")
