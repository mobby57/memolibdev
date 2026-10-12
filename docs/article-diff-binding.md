# Pourquoi votre IA de code a besoin d'un binding cryptographique

> Un patch peut être modifié entre l'approbation et l'application.
> Voici comment l'empêcher, en 30 lignes de Python.

## Le problème

Vous utilisez une IA pour générer du code. Vous validez un patch.
L'IA (ou un attaquant, ou un bug) l'applique.

**Question** : comment savez-vous que le patch appliqué est exactement
celui que vous avez validé ?

Réponse honnête : vous ne le savez pas.

## Ce que font les outils actuels

- **GitHub Copilot** : bouton "Apply". Aucune vérification du diff.
- **Cursor** : "Accept". Le patch est appliqué tel quel.
- **Devin** : "Approve". Le diff peut changer entre l'approbation et l'apply.

Le problème n'est pas l'IA. Le problème est qu'**aucun de ces outils ne
lie cryptographiquement l'approbation aux octets exacts du patch**.

## La solution : un hash canonique

```python
import hashlib

def canonical_diff_bytes(diff_text: str) -> bytes:
    """Octets canoniques du patch (aucune normalisation)."""
    if not isinstance(diff_text, str):
        raise TypeError("diff_text doit être une str")
    return diff_text.encode("utf-8")

def diff_sha256(diff_text: str) -> str:
    return hashlib.sha256(canonical_diff_bytes(diff_text)).hexdigest()
À l'approbation, on stocke expected_diff_sha256.

À l'application, on recalcule et on compare :

python
def verify_diff_binding(human_approval, diff_text) -> tuple[bool, str]:
    if human_approval.approved is not True:
        return False, "approbation non accordée"
    expected = human_approval.expected_diff_sha256
    if not expected:
        return False, "aucune empreinte enregistrée"
    actual = diff_sha256(diff_text)
    if actual != expected:
        return False, f"mismatch: attendu={expected[:16]} actuel={actual[:16]}"
    return True, "diff conforme"
Un seul octet change → hash différent → REFUS.

Le pattern fail-closed
python
REQUIRE_DIFF_BINDING = True

# Dans l'orchestrateur, AVANT toute écriture :
if not REQUIRE_DIFF_BINDING:
    return BLOCKED("binding obligatoire, aucun contournement")
Désactiver le binding ne le contourne pas : ça bloque l'application.
Il n'y a pas de chemin vers l'apply qui n'ait pas vérifié le hash.

Ce que ça change
Sans binding	Avec binding
Un patch modifié passe	REFUS immédiat
Confiance déclarative	Preuve mathématique
Audit impossible	SHA-256 exportable
DSI refuse	DSI peut auditer
Application
Cabinets d'avocats : traçabilité de chaque modification de code

Banques : conformité DORA, AI Act

Hôpitaux : audit des systèmes sensibles

Toute DSI qui a un jour eu un incident "qui a changé ce fichier ?"

Code complet
Voir coder_authorization.py dans MemoLibDev.

Licence propriétaire. Contact : morosidibepro@gmail.com