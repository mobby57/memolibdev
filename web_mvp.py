"""
MemoLibDev — web_mvp : front MVP d'interaction V0.1 (zéro dépendance)
=====================================================================

Front MINIMAL mais ROBUSTE (V0.1 « production-like ») posé AU-DESSUS de
l'API façade déjà validée. Un seul écran, une seule question, trois verbes :

    « Que voulez-vous que votre agent fasse ? »
        Comprendre | Proposer | Agir

RÈGLE GRAVÉE (non négociable) :
    « Front supprimable en totalité sans modifier ni affaiblir
      MemoLibDev Core. »

Le front reste STUPIDE. Toute la sécurité est côté serveur :
    - le navigateur ne décide JAMAIS d'une transition d'état ;
    - « Agir » ne veut pas dire « exécute maintenant » mais « prépare une
      action que je pourrai éventuellement autoriser » ;
    - l'autorisation passe par /approve, que le SERVEUR refuse si la
      mission n'est pas réellement en AWAITING_AUTHORIZATION ;
    - le refus passe par /reject ;
    - même si quelqu'un modifie ce JavaScript, AUCUNE nouvelle capacité
      n'apparaît (le moteur reste seul juge — prouvé par la validation
      adversariale de la frontière API).

Robustesse V0.1 (sans framework) :
    - aperçu OBLIGATOIRE avant toute approbation ;
    - boutons [Refuser] / [Autoriser] + avertissement d'effet ;
    - protection anti double-clic / double-submit (verrou d'UI) ;
    - timeout côté client (AbortController) + message lisible ;
    - affichage de l'état de mission renvoyé par le serveur ;
    - erreurs lisibles (jamais de trace technique brute) ;
    - Git/SHA/diff/D5.8/D5.9 restent invisibles.
"""

from __future__ import annotations

from typing import Optional, Tuple


_INDEX_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MemoLibDev</title>
<style>
  :root { --bg:#0f1115; --card:#171a21; --ink:#e8eaed; --muted:#9aa0a6;
          --accent:#4c8bf5; --ok:#36b37e; --warn:#e0a106; --err:#e5484d;
          --line:#262b33; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:16px/1.5 system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }
  .wrap { max-width:720px; margin:0 auto; padding:48px 20px 80px; }
  h1 { font-size:22px; font-weight:600; margin:0 0 24px; }
  label { display:block; color:var(--muted); font-size:14px; margin:0 0 8px; }
  textarea { width:100%; min-height:96px; resize:vertical; padding:14px;
             border-radius:12px; border:1px solid var(--line);
             background:var(--card); color:var(--ink); font:inherit; }
  .actions { display:flex; gap:12px; margin:16px 0 0; flex-wrap:wrap; }
  button { cursor:pointer; border:1px solid var(--line); background:var(--card);
           color:var(--ink); padding:12px 18px; border-radius:12px;
           font:inherit; font-weight:600; }
  button.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
  button.danger { background:transparent; border-color:var(--err); color:var(--err); }
  button:disabled { opacity:.45; cursor:not-allowed; }
  .card { margin-top:24px; background:var(--card); border:1px solid var(--line);
          border-radius:14px; padding:18px; }
  .card h2 { font-size:15px; margin:0 0 10px; color:var(--muted);
             text-transform:uppercase; letter-spacing:.04em; }
  .field { margin:10px 0; }
  .field .k { color:var(--muted); font-size:13px; }
  .field .v { white-space:pre-wrap; }
  ul.verif { margin:6px 0 0; padding-left:18px; }
  .badge { display:inline-block; padding:2px 10px; border-radius:999px;
           font-size:12px; font-weight:600; margin-left:8px; }
  .badge.ok { background:rgba(54,179,126,.15); color:var(--ok); }
  .badge.warn { background:rgba(224,161,6,.15); color:var(--warn); }
  .badge.err { background:rgba(229,72,77,.15); color:var(--err); }
  .warn-box { margin:14px 0; padding:12px 14px; border-radius:10px;
              background:rgba(224,161,6,.1); border:1px solid rgba(224,161,6,.4);
              color:#f0c868; }
  .approve { margin-top:16px; padding-top:16px; border-top:1px solid var(--line); }
  input[type=text] { width:100%; padding:12px; border-radius:10px;
                     border:1px solid var(--line); background:var(--bg);
                     color:var(--ink); font:inherit; }
  .row { display:flex; gap:12px; margin-top:12px; flex-wrap:wrap; }
  .hint { color:var(--muted); font-size:13px; margin:8px 0 0; }
  .spinner { color:var(--muted); font-size:14px; }
  .state { color:var(--muted); font-size:13px; margin-top:8px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Que voulez-vous que votre agent fasse&nbsp;?</h1>
  <label for="mission">Décrivez votre demande en langage courant</label>
  <textarea id="mission" placeholder="Ex. : expliquer ce que fait le fichier de connexion"></textarea>

  <div class="actions">
    <button id="btn-comprendre">Comprendre</button>
    <button id="btn-proposer">Proposer</button>
    <button id="btn-agir" class="primary">Agir</button>
  </div>
  <p class="hint">« Agir » <strong>prépare</strong> une action&nbsp;; rien n'est
     appliqué sans votre autorisation explicite.</p>

  <div id="out"></div>
</div>

<script>
"use strict";
// Le navigateur ne possède AUCUNE autorité. Il affiche et relaie. Toute
// décision de sécurité et toute transition d'état appartiennent au serveur.

const CLIENT_TIMEOUT_MS = 120000;   // garde-fou client ; le serveur a le sien.

const out = document.getElementById("out");
const missionEl = document.getElementById("mission");
const allButtons = ["btn-comprendre", "btn-proposer", "btn-agir"]
  .map(id => document.getElementById(id));

let busy = false;              // verrou anti double-submit (UI uniquement)
let currentRunId = null;       // run_id courant (jamais montré à l'utilisateur)

function setBusy(v) {
  busy = v;
  allButtons.forEach(b => { b.disabled = v; });
}

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;   // textContent => pas d'injection HTML
  return n;
}

function badgeClass(etat) {
  const ok = ["APPLIED", "ANALYZED", "OK", "COMPLETED"];
  const warn = ["AWAIT_HUMAN", "QUESTION", "NO_PATCH_POSSIBLE",
                "AWAITING_AUTHORIZATION", "PROPOSAL_READY"];
  if (ok.includes(etat)) return "ok";
  if (warn.includes(etat)) return "warn";
  return "err";
}

function clearOut() { out.innerHTML = ""; }

function showLoading(label) {
  clearOut();
  out.appendChild(el("div", "spinner", "… " + label));
}

function field(parent, k, v) {
  if (v == null || v === "" || (Array.isArray(v) && v.length === 0)) return;
  const f = el("div", "field");
  f.appendChild(el("div", "k", k));
  if (Array.isArray(v)) {
    const ul = el("ul", "verif");
    v.forEach(x => ul.appendChild(el("li", null, String(x))));
    f.appendChild(ul);
  } else {
    f.appendChild(el("div", "v", String(v)));
  }
  parent.appendChild(f);
}

function renderError(payload) {
  clearOut();
  const card = el("div", "card");
  const h = el("h2", null, "Erreur");
  card.appendChild(h);
  h.appendChild(el("span", "badge err", payload.error || "ERREUR"));
  // Message lisible : jamais de trace technique brute.
  field(card, "Détail", payload.reason || "Requête invalide.");
  out.appendChild(card);
}

// fetch avec timeout client (AbortController) + JSON tolérant.
async function callApi(path, body) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), CLIENT_TIMEOUT_MS);
  try {
    const resp = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    const data = await resp.json().catch(() => ({}));
    return { httpStatus: resp.status, data };
  } finally {
    clearTimeout(timer);
  }
}

function missionText() { return (missionEl.value || "").trim(); }

// --- COMPRENDRE / PROPOSER : un seul appel /mission, affichage direct ---
async function runMission(mode, titre) {
  if (busy) return;
  const mission = missionText();
  if (!mission) { renderError({ error: "VIDE", reason: "Décrivez d'abord votre demande." }); return; }
  setBusy(true);
  showLoading(titre + " en cours");
  try {
    const { httpStatus, data } = await callApi("/mission", { mission, mode });
    if (httpStatus !== 200) { renderError(data); return; }
    currentRunId = data.run_id || null;
    clearOut();
    out.appendChild(renderResult(data, titre));
  } catch (e) {
    renderError({ error: "DELAI_OU_RESEAU",
      reason: (e && e.name === "AbortError")
        ? "La demande a pris trop de temps et a été interrompue. Réessayez."
        : "Problème de communication avec l'agent." });
  } finally {
    setBusy(false);
  }
}

// --- AGIR : étape 1 => aperçu. Jamais le nom avant l'aperçu. ---
async function runAgirPreview() {
  if (busy) return;
  const mission = missionText();
  if (!mission) { renderError({ error: "VIDE", reason: "Décrivez d'abord votre demande." }); return; }
  setBusy(true);
  showLoading("Préparation de l'action");
  currentRunId = null;
  try {
    // Le serveur PRÉPARE (SUPERVISED_APPLY) et s'arrête AVANT toute
    // écriture : il passe en AWAITING_AUTHORIZATION. Le front n'approuve
    // jamais seul ; il affiche l'aperçu et propose Refuser / Autoriser.
    const { httpStatus, data } = await callApi("/mission",
      { mission, mode: "SUPERVISED_APPLY" });
    if (httpStatus !== 200) { renderError(data); return; }
    currentRunId = data.run_id || null;
    clearOut();
    out.appendChild(renderAgirPreview(data));
  } catch (e) {
    renderError({ error: "DELAI_OU_RESEAU",
      reason: (e && e.name === "AbortError")
        ? "La préparation a pris trop de temps et a été interrompue. Réessayez."
        : "Problème de communication avec l'agent." });
  } finally {
    setBusy(false);
  }
}

// --- AGIR : étape 2a => /approve avec le nom saisi (jamais fabriqué ici). ---
async function runApprove(approver) {
  if (busy) return;
  const name = (approver || "").trim();
  if (!name) { renderError({ error: "NOM_MANQUANT", reason: "Saisissez un nom pour autoriser." }); return; }
  if (!currentRunId) { renderError({ error: "AUCUN_APERCU", reason: "Préparez d'abord une action (Agir)." }); return; }
  setBusy(true);
  showLoading("Autorisation et exécution contrôlée");
  try {
    const { httpStatus, data } = await callApi("/approve",
      { run_id: currentRunId, approver: name });
    if (httpStatus !== 200) { renderError(data); return; }
    clearOut();
    out.appendChild(renderActionDone(data));
  } catch (e) {
    renderError({ error: "DELAI_OU_RESEAU",
      reason: (e && e.name === "AbortError")
        ? "L'exécution a pris trop de temps côté client. Vérifiez le résultat avant de réessayer."
        : "Problème de communication avec l'agent." });
  } finally {
    setBusy(false);
  }
}

// --- AGIR : étape 2b => /reject (refus terminal, sans exécution). ---
async function runReject() {
  if (busy) return;
  if (!currentRunId) { renderError({ error: "AUCUN_APERCU", reason: "Rien à refuser." }); return; }
  setBusy(true);
  showLoading("Annulation");
  try {
    const { httpStatus, data } = await callApi("/reject", { run_id: currentRunId });
    clearOut();
    const card = el("div", "card");
    const h = el("h2", null, "Action refusée");
    h.appendChild(el("span", "badge warn", (data && data.state) || "REFUSED"));
    card.appendChild(h);
    field(card, "Résultat", "Aucune modification n'a été effectuée. Votre projet est inchangé.");
    out.appendChild(card);
    currentRunId = null;
  } catch (e) {
    renderError({ error: "RESEAU", reason: "Problème de communication avec l'agent." });
  } finally {
    setBusy(false);
  }
}

// --- Rendus ---

function resultCard(titre, etat) {
  const card = el("div", "card");
  const h = el("h2", null, titre);
  h.appendChild(el("span", "badge " + badgeClass(etat), etat));
  card.appendChild(h);
  return card;
}

function renderResult(data, titre) {
  const vue = data.vue || {};
  const card = resultCard(titre, data.status);
  field(card, "Ce que j'ai compris", vue.ce_que_j_ai_compris);
  field(card, "Ce que je vais faire", vue.ce_que_je_vais_faire);
  field(card, "Pourquoi", vue.pourquoi);
  field(card, "Vérifié", vue.ce_qui_a_ete_verifie);
  field(card, "Résultat", vue.resultat);
  if (vue.action_requise) field(card, "Action requise", vue.action_requise);
  return card;
}

function renderAgirPreview(data) {
  const vue = data.vue || {};
  const preview = data.preview || {};
  const card = resultCard("Voici ce que mon agent propose de faire", data.status);
  field(card, "Fichier concerné", preview.fichier_concerne);
  field(card, "Pourquoi", preview.pourquoi || vue.pourquoi);
  field(card, "Résultat attendu", preview.resultat_attendu || vue.resultat);

  // L'autorisation n'est proposée QUE si le SERVEUR le permet (can_approve).
  // Le navigateur ne force jamais cette possibilité.
  if (data.can_approve) {
    const warn = el("div", "warn-box",
      "⚠️ Cette action modifiera votre projet. Elle ne sera exécutée "
      + "qu'après votre autorisation explicite.");
    card.appendChild(warn);

    const ap = el("div", "approve");
    ap.appendChild(el("div", "k", "Pour autoriser, saisissez votre nom :"));
    const name = el("input"); name.type = "text";
    name.placeholder = "Nom de l'approbateur";
    ap.appendChild(name);

    const row = el("div", "row");
    const refuse = el("button", "danger", "Refuser");
    refuse.addEventListener("click", runReject);
    const allow = el("button", "primary", "Autoriser");
    allow.addEventListener("click", () => runApprove(name.value));
    row.appendChild(refuse);
    row.appendChild(allow);
    ap.appendChild(row);

    ap.appendChild(el("p", "hint",
      "Votre nom n'accorde aucun pouvoir : il enregistre votre décision. "
      + "Le moteur reste seul juge et peut refuser."));
    card.appendChild(ap);
  } else {
    // Le serveur n'autorise pas d'approbation ici (ex. BLOQUÉ / QUESTION).
    field(card, "Résultat", vue.resultat);
    if (vue.action_requise) field(card, "Action requise", vue.action_requise);
  }
  return card;
}

function renderActionDone(data) {
  const vue = data.vue || {};
  const etat = data.state || data.status;
  const card = resultCard("Résultat", etat);
  if (data.status === "APPLIED" || etat === "COMPLETED") {
    field(card, null, "✓ Modification effectuée");
    field(card, null, "✓ Vérification réussie");
    field(card, null, "✓ Projet cohérent");
  }
  field(card, "Détail", vue.resultat);
  if (vue.action_requise) field(card, "Action requise", vue.action_requise);
  return card;
}

document.getElementById("btn-comprendre")
  .addEventListener("click", () => runMission("READ_ONLY", "Comprendre"));
document.getElementById("btn-proposer")
  .addEventListener("click", () => runMission("PROPOSE", "Proposer"));
document.getElementById("btn-agir")
  .addEventListener("click", runAgirPreview);
</script>
</body>
</html>
"""


def static_provider(path: str) -> Optional[Tuple[str, bytes]]:
    """
    Sert la page unique du MVP. Lecture seule, octets statiques, aucune
    logique de sécurité. `path` normalisé sans query/fragment. Toute autre
    route -> None (le serveur renverra 404).
    """
    clean = (path or "/").split("?", 1)[0].split("#", 1)[0]
    if clean in ("/", "/index.html"):
        return ("text/html; charset=utf-8", _INDEX_HTML.encode("utf-8"))
    return None


def serve_mvp(host: str = "127.0.0.1", port: int = 8765, facade=None) -> None:
    """
    Lance l'API façade AVEC le front MVP (GET / => écran unique). La
    sécurité, les états et /mission, /approve, /reject restent STRICTEMENT
    ceux d'api_facade. En production, passer une `facade` dotée d'un
    provider_factory réel.
    """
    from api_facade import serve, ApiFacade
    serve(host=host, port=port, facade=facade or ApiFacade(),
          static_provider=static_provider)


if __name__ == "__main__":
    serve_mvp()
