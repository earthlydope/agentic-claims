import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

export type Lang = 'en' | 'de'

/**
 * The platform speaks German because its users do. Austrian insurance has settled
 * vocabulary — Schadenfall, Selbstbehalt, Sachverständiger, Polizze — and translating it
 * loosely would make the German read like a translation. So the German column here is the
 * term the trade actually uses, not the dictionary equivalent of the English.
 */
const DICT: Record<string, [string, string]> = {
  // ── shell ─────────────────────────────────────────────────────────
  'app.name': ['Agentic Claims', 'Agentic Claims'],
  'app.region': ['EU · europe-west4', 'EU · europe-west4'],
  'shell.collapse': ['Collapse', 'Einklappen'],
  'shell.expand': ['Expand', 'Ausklappen'],
  'shell.switchRole': ['Switch role', 'Rolle wechseln'],
  'shell.current': ['current', 'aktiv'],
  'shell.language': ['Language', 'Sprache'],
  'shell.reset': ['Reset demo data', 'Demodaten zurücksetzen'],
  'shell.resetting': ['Resetting…', 'Wird zurückgesetzt…'],
  'shell.signedInAs': ['You are signed in as', 'Sie sind angemeldet als'],
  'shell.noAuthority': ['No settlement authority', 'Keine Zahlungsvollmacht'],
  'shell.authorityUpTo': ['Approves up to', 'Genehmigt bis'],

  // ── roles ─────────────────────────────────────────────────────────
  'role.policy_holder': ['Policy Holder', 'Versicherungsnehmer'],
  'role.claim_handler': ['Claim Handler', 'Sachbearbeiter'],
  'role.motor_assessor': ['Motor Assessor', 'Kfz-Sachverständiger'],
  'role.siu': ['Special Investigations', 'Sonderermittlung'],
  'role.compliance_ops': ['Compliance & Operations', 'Compliance & Betrieb'],

  // ── navigation ────────────────────────────────────────────────────
  'nav.my_claims': ['My claims', 'Meine Schadensfälle'],
  'nav.my_policies': ['My policies', 'Meine Polizzen'],
  'nav.file_claim': ['Report a claim', 'Schaden melden'],
  'nav.work_queue': ['My work', 'Meine Arbeit'],
  'nav.assessment_queue': ['Assessments', 'Begutachtungen'],
  'nav.approvals': ['Approvals', 'Genehmigungen'],
  'nav.investigations': ['Referrals', 'Prüffälle'],
  'nav.recovery': ['Recovery', 'Regress'],
  'nav.operations': ['Operations', 'Betrieb'],
  'nav.governance': ['Assurance', 'Kontrolle'],
  'nav.model_usage': ['Assistant usage', 'Assistenz-Nutzung'],

  'navhint.my_claims': ['Where each of your claims stands', 'Der Stand Ihrer Schadensfälle'],
  'navhint.my_policies': ['What you are covered for, and the documents',
                          'Ihr Versicherungsschutz und Ihre Dokumente'],
  'navhint.file_claim': ['Tell us what happened', 'Erzählen Sie uns, was passiert ist'],
  'navhint.work_queue': ['Claims waiting on you', 'Fälle, die auf Sie warten'],
  'navhint.assessment_queue': ['Damage and repairability', 'Schaden und Reparaturfähigkeit'],
  'navhint.approvals': ['Above handler authority', 'Über der Sachbearbeitervollmacht'],
  'navhint.investigations': ['Referred for a closer look', 'Zur näheren Prüfung vorgelegt'],
  'navhint.recovery': ['Money to recover from a third party', 'Regress gegenüber Dritten'],
  'navhint.operations': ['Throughput, SLA and where automation stops',
                         'Durchlauf, SLA und wo die Automatisierung endet'],
  'navhint.governance': ['What is enforced, the audit trail, and the drills',
                         'Was durchgesetzt wird, das Prüfprotokoll und die Tests'],
  'navhint.model_usage': ['Limits, consumption and cost per claim',
                          'Limits, Verbrauch und Kosten je Schadensfall'],

  // ── my claims ─────────────────────────────────────────────────────
  'claims.title': ['My claims', 'Meine Schadensfälle'],
  'claims.none': ['You have no claims.', 'Sie haben keine Schadensfälle.'],
  'claims.noneHint': ['If something has happened to your car, report it here.',
                      'Wenn Ihrem Fahrzeug etwas passiert ist, melden Sie es hier.'],
  'claims.report': ['Report a claim', 'Schaden melden'],
  'claims.reported': ['Reported', 'Gemeldet'],
  'claims.open': ['Open', 'Offen'],
  'claims.settled': ['Paid', 'Ausbezahlt'],
  'claims.yourExcess': ['Your excess', 'Ihr Selbstbehalt'],
  'claims.payout': ['Payment to you', 'Zahlung an Sie'],
  'claims.whatNext': ['What happens next', 'Wie es weitergeht'],
  'claims.weNeed': ['We still need', 'Wir benötigen noch'],
  'claims.nothingNeeded': ['Nothing — we have what we need.',
                           'Nichts — wir haben alles, was wir brauchen.'],
  'claims.send': ['Send what we asked for', 'Gewünschte Unterlagen senden'],
  'claims.sendHint': ['Add the document or answer we asked for, and we carry on from there.',
                      'Fügen Sie die angeforderte Unterlage oder Antwort hinzu — wir machen '
                      + 'dann weiter.'],
  'claims.yourAnswer': ['Anything you want to tell us', 'Was Sie uns mitteilen möchten'],
  'claims.policeRef': ['Police reference, if you have one', 'Aktenzahl der Polizei, falls vorhanden'],
  'claims.sending': ['Sending…', 'Wird gesendet…'],
  'claims.sent': ['Thank you — we have it and we are carrying on.',
                  'Danke — wir haben es erhalten und machen weiter.'],
  'claims.cancel': ['Cancel', 'Abbrechen'],
  'claims.viewDetail': ['Open', 'Öffnen'],

  // ── my policies ───────────────────────────────────────────────────
  'pol.title': ['My policies', 'Meine Polizzen'],
  'pol.none': ['No policies on this account.', 'Keine Polizzen auf diesem Konto.'],
  'pol.active': ['Active', 'Aktiv'],
  'pol.lapsed': ['Lapsed', 'Erloschen'],
  'pol.vehicle': ['Vehicle', 'Fahrzeug'],
  'pol.premium': ['Premium', 'Prämie'],
  'pol.perYear': ['per year', 'pro Jahr'],
  'pol.excess': ['Excess', 'Selbstbehalt'],
  'pol.excessHint': ['What you pay towards each claim',
                     'Ihr Eigenanteil je Schadensfall'],
  'pol.sumInsured': ['Sum insured', 'Versicherungssumme'],
  'pol.covered': ['You are covered for', 'Versichert sind'],
  'pol.notCovered': ['Not covered', 'Nicht versichert'],
  'pol.extras': ['Add-ons', 'Zusatzbausteine'],
  'pol.ncd': ['No-claims years', 'Schadenfreie Jahre'],
  'pol.ncdProtected': ['protected', 'geschützt'],
  'pol.renews': ['Renews', 'Erneuert am'],
  'pol.since': ['Since', 'Seit'],
  'pol.document': ['Policy document', 'Polizze'],
  'pol.view': ['View', 'Ansehen'],
  'pol.download': ['Download', 'Herunterladen'],
  'pol.claimOnThis': ['Report a claim on this policy',
                      'Schaden zu dieser Polizze melden'],
  'pol.openClaim': ['Open claim', 'Offener Schadensfall'],

  // ── report a claim ────────────────────────────────────────────────
  'file.title': ['Report a claim', 'Schaden melden'],
  'file.lead': ['Three steps. It takes a few minutes.',
                'Drei Schritte. Es dauert wenige Minuten.'],
  'file.step1': ['Which vehicle?', 'Welches Fahrzeug?'],
  'file.step2': ['What happened?', 'Was ist passiert?'],
  'file.step3': ['Anything to attach?', 'Unterlagen beifügen?'],
  'file.pickPolicy': ['Choose the policy', 'Polizze auswählen'],
  'file.orUpload': ['Or upload your policy document',
                    'Oder laden Sie Ihre Polizze hoch'],
  'file.uploadPolicyHint': ['If your policy is not listed, upload the document and we will '
                            + 'read it.',
                            'Wenn Ihre Polizze nicht aufgeführt ist, laden Sie das Dokument '
                            + 'hoch — wir lesen es aus.'],
  'file.tellUs': ['Tell us in your own words', 'Erzählen Sie es in Ihren Worten'],
  'file.answerQuestions': ['Answer a few questions', 'Ein paar Fragen beantworten'],
  'file.fillForm': ['Fill in the form', 'Formular ausfüllen'],
  'file.formHint': ['If you would rather type the details yourself.',
                    'Wenn Sie die Angaben selbst eintragen möchten.'],
  'file.questionsHint': ['We ask one question at a time, based on what you have already '
                         + 'told us.',
                         'Wir stellen eine Frage nach der anderen — je nachdem, was Sie '
                         + 'bereits erzählt haben.'],
  'file.freeText': ['What happened?', 'Was ist passiert?'],
  'file.freeTextPlaceholder': [
    'For example: I was reversing out of a parking space in Vienna on Tuesday morning and '
    + 'hit a bollard. The rear bumper is dented.',
    'Zum Beispiel: Ich bin am Dienstagmorgen in Wien aus einer Parklücke zurückgesetzt und '
    + 'gegen einen Poller gefahren. Die Heckstoßstange ist eingedellt.',
  ],
  'file.attach': ['Add photos, a repair quote, a police report',
                  'Fotos, Kostenvoranschlag, Polizeianzeige hinzufügen'],
  'file.attachHint': ['Optional, but a claim with a quote and clear photos is settled '
                      + 'faster.',
                      'Optional — mit Kostenvoranschlag und klaren Fotos geht es schneller.'],
  'file.drop': ['Drop files here, or', 'Dateien hier ablegen, oder'],
  'file.browse': ['browse', 'durchsuchen'],
  'file.submit': ['Submit my claim', 'Schaden absenden'],
  'file.submitting': ['Submitting…', 'Wird gesendet…'],
  'file.next': ['Next', 'Weiter'],
  'file.back': ['Back', 'Zurück'],
  'file.reviewing': ['We are reading your documents…',
                     'Wir lesen Ihre Unterlagen…'],
  'file.thanks': ['Thank you — your claim is with us.',
                  'Danke — Ihr Schaden ist bei uns eingegangen.'],
  'file.reference': ['Your reference', 'Ihre Schadensnummer'],
  'file.weWillWrite': ['We will write to you. You can follow it under My claims at any '
                       + 'time.',
                       'Wir melden uns bei Ihnen. Den Stand sehen Sie jederzeit unter '
                       + '„Meine Schadensfälle“.'],
  'file.followIt': ['Follow my claim', 'Schadensfall verfolgen'],

  // ── questionnaire ─────────────────────────────────────────────────
  'q.thinking': ['…', '…'],
  'q.yourAnswer': ['Your answer', 'Ihre Antwort'],
  'q.send': ['Send', 'Senden'],
  'q.skip': ['I do not know', 'Weiß ich nicht'],
  'q.done': ['That is everything we need.', 'Das ist alles, was wir brauchen.'],
  'q.switchToForm': ['Use the form instead', 'Stattdessen das Formular nutzen'],

  // ── claim detail, shared ──────────────────────────────────────────
  'cl.back': ['Back', 'Zurück'],
  'cl.status': ['Status', 'Status'],
  'cl.decision': ['Decision', 'Entscheidung'],
  'cl.incident': ['The incident', 'Der Schadensfall'],
  'cl.asReported': ['As reported', 'Wie gemeldet'],
  'cl.cover': ['Cover', 'Deckung'],
  'cl.damage': ['Damage', 'Schaden'],
  'cl.estimate': ['Estimate', 'Kostenvoranschlag'],
  'cl.risk': ['Risk', 'Risiko'],
  'cl.settlement': ['Settlement', 'Abrechnung'],
  'cl.documents': ['Documents', 'Unterlagen'],
  'cl.message': ['Message to the customer', 'Nachricht an den Kunden'],
  'cl.copy': ['Copy', 'Kopieren'],
  'cl.copied': ['Copied', 'Kopiert'],
  'cl.working': ['Working on it…', 'Wird bearbeitet…'],
  'cl.autoStarted': ['We started as soon as your documents arrived.',
                     'Wir haben begonnen, sobald Ihre Unterlagen eingegangen sind.'],
  'cl.whyThis': ['Why this?', 'Warum?'],
  'cl.whatWentIn': ['What went in', 'Grundlage'],
  'cl.whatCameOut': ['What came out', 'Ergebnis'],
  'cl.basedOn': ['Based on', 'Auf Basis von'],
  'cl.helpful': ['Helpful', 'Hilfreich'],
  'cl.notHelpful': ['Not helpful', 'Nicht hilfreich'],
  'cl.rated': ['Thanks — noted.', 'Danke — vermerkt.'],
  'cl.confidence': ['Confidence', 'Konfidenz'],
  'cl.clause': ['Clause', 'Klausel'],
  'cl.heldBecause': ['Held because', 'Zurückgehalten, weil'],
  'cl.wouldClear': ['To clear it', 'Zur Freigabe'],

  // ── coworker dock ─────────────────────────────────────────────────
  'cw.open': ['Ask for help', 'Hilfe holen'],
  'cw.close': ['Close', 'Schließen'],
  'cw.placeholder': ['Ask a question…', 'Frage stellen…'],
  'cw.tryAsking': ['Try asking', 'Fragen Sie zum Beispiel'],
  'cw.thinking': ['Thinking…', 'Denkt nach…'],
  'cw.needsPerson': ['A person should look at this.',
                     'Das sollte sich ein Mensch ansehen.'],
  'cw.basedOn': ['Based on', 'Grundlage'],
  'cw.blocked': ['That question was not passed on.',
                 'Diese Frage wurde nicht weitergegeben.'],
  'cw.clear': ['New conversation', 'Neues Gespräch'],
  'cw.cannot': ['It cannot', 'Nicht möglich'],

  // ── work queues and operations ────────────────────────────────────
  'wq.myDesk': ['My desk',
   'Mein Schreibtisch'],
  'wq.myDeskLede': ['Claims the platform could not finish on its own. Each one says which check stopped it, so you are not guessing why it arrived.',
   'Fälle, die das System nicht selbst abschließen konnte. Bei jedem steht, welche Prüfung ihn gestoppt hat — Sie müssen nicht raten.'],
  'wq.myDeskEmpty': ['Nothing on your desk. Every claim the platform could finish, it finished.',
   'Nichts auf Ihrem Schreibtisch. Alles, was das System abschließen konnte, ist abgeschlossen.'],
  'wq.assess': ['Assessments',
   'Begutachtungen'],
  'wq.assessLede': ['Damage, estimates and the repairability call. You own the technical position; the settlement is somebody else’s.',
   'Schaden, Kostenvoranschlag und Reparaturfähigkeit. Die technische Beurteilung liegt bei Ihnen, die Abrechnung nicht.'],
  'wq.assessEmpty': ['No assessments waiting. Nothing has needed a technical opinion.',
   'Keine offenen Begutachtungen. Es war noch kein Gutachten nötig.'],
  'wq.approvals': ['Approvals',
   'Genehmigungen'],
  'wq.approvalsLede': ['Decisions above handler authority. What was proposed sits next to the check that stopped it.',
   'Entscheidungen über der Sachbearbeitervollmacht. Der Vorschlag steht neben der Prüfung, die ihn gestoppt hat.'],
  'wq.approvalsEmpty': ['Nothing waiting on your approval.',
   'Keine Genehmigung ausstehend.'],
  'wq.siu': ['Referrals',
   'Prüffälle'],
  'wq.siuLede': ['Referrals from handlers and from the platform’s own signals. Signals, not findings — the claim is frozen, not declined.',
   'Vorlagen von Sachbearbeitern und aus den Signalen des Systems. Signale, keine Feststellungen — der Fall ist gesperrt, nicht abgelehnt.'],
  'wq.siuEmpty': ['No referrals open.',
   'Keine offenen Prüffälle.'],
  'wq.recovery': ['Recovery',
   'Regress'],
  'wq.recoveryLede': ['Settled claims where a third party may owe us — including the excess your customer is out of pocket for.',
   'Abgerechnete Fälle mit möglichem Regress gegen Dritte — einschließlich des Selbstbehalts, den Ihr Kunde getragen hat.'],
  'wq.recoveryEmpty': ['Nothing to recover on at the moment.',
   'Derzeit kein Regress offen.'],
  'wq.open': ['Open',
   'Offen'],
  'wq.valueAtStake': ['Value at stake',
   'Betroffene Summe'],
  'wq.pastSla': ['Past SLA',
   'SLA überschritten'],
  'wq.withinAuth': ['Within my authority',
   'In meiner Vollmacht'],
  'wq.ofWaiting': ['of {n} waiting',
   'von {n} offen'],
  'wq.noAuthority': ['this role does not settle',
   'diese Rolle rechnet nicht ab'],
  'wq.prioritised': ['Prioritised',
   'Priorisiert'],
  'wq.prioritisedBy': ['Value, SLA, risk, failed automation',
   'Summe, SLA, Risiko, fehlgeschlagene Automatisierung'],
  'wq.refresh': ['Refresh',
   'Aktualisieren'],
  'wq.openClaim': ['Open the claim',
   'Fall öffnen'],
  'wq.policyholder': ['Policyholder',
   'Versicherungsnehmer'],
  'wq.proposed': ['Proposed',
   'Vorgeschlagen'],
  'wq.amount': ['Amount',
   'Betrag'],
  'wq.needs': ['Needs',
   'Benötigt'],
  'wq.age': ['Age',
   'Alter'],
  'wq.cover': ['Cover',
   'Deckung'],
  'wq.estimate': ['Estimate',
   'Kostenvoranschlag'],
  'wq.risk': ['Risk',
   'Risiko'],
  'wq.decision': ['Decision',
   'Entscheidung'],
  'wq.stagesOwned': ['The stages you own',
   'Ihre Zuständigkeiten'],
  'wq.stagesOwnedHint': ['Everything else on the claim belongs to somebody else, and the platform keeps it that way.',
   'Alles Übrige am Fall gehört einer anderen Rolle — und das System hält sich daran.'],
  'wq.aboveAuthority': ['Above your authority',
   'Über Ihrer Vollmacht'],
  'wq.notYourCall': ['Not your call, by design',
   'Bewusst nicht Ihre Entscheidung'],
  'wq.amountToSettle': ['Amount to settle',
   'Abzurechnender Betrag'],
  'wq.noteForRecord': ['Note for the record',
   'Aktennotiz'],
  'wq.whyThisDecision': ['Why this decision',
   'Begründung'],
  'wq.approve': ['Approve',
   'Genehmigen'],
  'wq.reject': ['Reject',
   'Ablehnen'],
  'wq.askForMore': ['Ask for more',
   'Nachfordern'],
  'wq.refused': ['Refused',
   'Abgewiesen'],
  'wq.writtenSigned': ['Written once, signed',
   'Einmal geschrieben, signiert'],
  'wq.samePath': ['A human decision travels the same path as an autonomous one',
   'Eine menschliche Entscheidung nimmt denselben Weg wie eine automatische'],
  'wq.approver': ['Approver',
   'Genehmiger'],
  'wq.settled': ['Settled',
   'Abgerechnet'],
  'wq.approval': ['Approval',
   'Genehmigung'],
  'wq.rowAudit': ['Row audit',
   'Datensatzprüfung'],
  'tv.title': ['Operations',
   'Betrieb'],
  'tv.fiveMeasures': ['The five measures',
   'Die fünf Kennzahlen'],
  'tv.computedFrom': ['Each computed from claim rows rather than asserted',
   'Jede aus den Falldaten berechnet, nicht behauptet'],
  'tv.openByQueue': ['Open work by queue',
   'Offene Arbeit je Warteschlange'],
  'tv.andWhatAtStake': ['And what is at stake on each',
   'Und die betroffene Summe je Warteschlange'],
  'tv.whereStopped': ['Where automation stopped',
   'Wo die Automatisierung endete'],

  'wq.selectOne': ['Select an item.', 'Wählen Sie einen Eintrag.'],
  'wq.authority': ['Authority',
   'Vollmacht'],
  'wq.adverseNote': ['An adverse outcome is never issued autonomously — a named person confirms it.',
   'Eine nachteilige Entscheidung wird nie automatisch erlassen — ein benannter Mensch bestätigt sie.'],
  'wq.writeNote': ['Whatever you choose, the write is signed, verified at the gateway and written once.',
   'Was Sie auch wählen: der Schreibvorgang wird signiert, am Gateway geprüft und genau einmal ausgeführt.'],
  'wq.noSignals': ['No signals.',
   'Keine Signale.'],
  'wq.threshold': ['threshold',
   'Schwelle'],
  'wq.withinBand': ['within expected band',
   'im erwarteten Rahmen'],
  'wq.outsideBand': ['outside expected band',
   'außerhalb des erwarteten Rahmens'],
  'wq.parts': ['parts',
   'Teile'],
  'wq.labour': ['labour',
   'Arbeit'],
  'wq.vat': ['VAT',
   'USt.'],

  // ── the claim file ────────────────────────────────────────────────
  'cw2.policyholder': ['Policyholder',
   'Versicherungsnehmer'],
  'cw2.policy': ['Policy',
   'Polizze'],
  'cw2.vehicle': ['Vehicle',
   'Fahrzeug'],
  'cw2.excess': ['Excess',
   'Selbstbehalt'],
  'cw2.reported': ['Reported',
   'Gemeldet'],
  'cw2.flags': ['Flags',
   'Hinweise'],
  'cw2.customerWrote': ['What the customer wrote',
   'Was der Kunde geschrieben hat'],
  'cw2.tabResults': ['What was found',
   'Was festgestellt wurde'],
  'cw2.tabRun': ['Step by step',
   'Schritt für Schritt'],
  'cw2.tabEvidence': ['Documents',
   'Unterlagen'],
  'cw2.tabAssessment': ['Assessment',
   'Begutachtung'],
  'cw2.tabDecision': ['Decision & checks',
   'Entscheidung & Prüfungen'],
  'cw2.tabCustomer': ['Customer',
   'Kunde'],
  'cw2.tabLedger': ['Audit trail',
   'Prüfprotokoll'],
  'cw2.back': ['Claims',
   'Schadensfälle'],
  'cw2.working': ['Working on it…',
   'Wird bearbeitet…'],
  'cw2.none': ['none',
   'keine'],
  'cw2.notWorked': ['This claim has not been worked yet.',
   'Dieser Fall wurde noch nicht bearbeitet.'],
  'cw2.startsOnOwn': ['Analysis starts on its own when a claim is notified. If nothing is shown here, it has not reached this file yet.',
   'Die Bearbeitung beginnt automatisch mit der Meldung. Steht hier nichts, hat sie diesen Akt noch nicht erreicht.'],
  'cw2.readingNow': ['Reading the file now — results appear here as each stage finishes.',
   'Der Akt wird gerade gelesen — Ergebnisse erscheinen hier, sobald jeder Schritt fertig ist.'],
  'cw2.nothingAssessed': ['Nothing has been assessed on this claim yet.',
   'An diesem Fall wurde noch nichts geprüft.'],

  // ── assurance and usage ───────────────────────────────────────────
  'zt.title': ['Assurance',
   'Kontrolle'],
  'zt.lede': ['Every prompt, every tool call and every write passes through here. Prompt instructions are never the security boundary — each control passes or fails a test rather than being a paragraph of assurance.',
   'Jede Eingabe, jeder Werkzeugaufruf und jeder Schreibvorgang läuft hier durch. Anweisungen im Prompt sind nie die Sicherheitsgrenze — jede Kontrolle besteht einen Test oder fällt durch, statt eine Zusicherung im Text zu sein.'],
  'mu.title': ['Assistant usage',
   'Assistenz-Nutzung'],
  'mu.lede': ['What the platform consumed, what it cost per claim, and how much headroom is left before capacity starts refusing us.',
   'Was das System verbraucht hat, was es je Schadensfall gekostet hat, und wie viel Spielraum bleibt, bevor die Kapazität nicht mehr ausreicht.'],

  // ── generic ───────────────────────────────────────────────────────
  'g.loading': ['Loading…', 'Wird geladen…'],
  'g.retry': ['Try again', 'Erneut versuchen'],
  'g.none': ['None', 'Keine'],
  'g.yes': ['Yes', 'Ja'],
  'g.no': ['No', 'Nein'],
  'g.of': ['of', 'von'],
  'g.showMore': ['Show more', 'Mehr anzeigen'],
  'g.showLess': ['Show less', 'Weniger anzeigen'],
  'g.today': ['today', 'heute'],
  'g.days': ['days', 'Tage'],
  'g.hours': ['hours', 'Stunden'],
  'g.minutes': ['minutes', 'Minuten'],
  'g.overdue': ['overdue', 'überfällig'],
}

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (key: string, fallback?: string) => string }

const LanguageContext = createContext<Ctx>({
  lang: 'en',
  setLang: () => undefined,
  t: (k) => k,
})

const STORE_KEY = 'agentic-claims.lang'

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    try {
      const saved = window.localStorage.getItem(STORE_KEY)
      if (saved === 'de' || saved === 'en') return saved
      // An Austrian browser gets German without being asked.
      return navigator.language?.toLowerCase().startsWith('de') ? 'de' : 'en'
    } catch {
      return 'en'
    }
  })

  const setLang = useCallback((next: Lang) => {
    setLangState(next)
    try {
      window.localStorage.setItem(STORE_KEY, next)
    } catch {
      /* private browsing */
    }
  }, [])

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  const t = useCallback(
    (key: string, fallback?: string) => {
      const row = DICT[key]
      if (!row) return fallback ?? key
      return row[lang === 'de' ? 1 : 0] || row[0]
    },
    [lang],
  )

  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t])
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

export function useLang() {
  return useContext(LanguageContext)
}

/** Just the translator, for the common case. */
export function useT() {
  return useContext(LanguageContext).t
}

/** Locale-aware money, so EUR 1.234,56 reads correctly in German. */
export function useMoney() {
  const { lang } = useLang()
  return useCallback(
    // Accepts either a decimal count or {decimals}, so it is a drop-in for the plain
    // formatter it replaced across the views.
    (n: number | null | undefined, opts: number | { decimals?: boolean } = {}) => {
      if (n === null || n === undefined) return '—'
      const places =
        typeof opts === 'number' ? opts : opts.decimals ? 2 : 0
      return new Intl.NumberFormat(lang === 'de' ? 'de-AT' : 'en-IE', {
        style: 'currency',
        currency: 'EUR',
        minimumFractionDigits: places,
        maximumFractionDigits: places,
      }).format(n)
    },
    [lang],
  )
}

/** Locale-aware dates. */
export function useDate() {
  const { lang } = useLang()
  return useCallback(
    (iso: string | null | undefined, opts: { withTime?: boolean } = {}) => {
      if (!iso) return '—'
      const d = new Date(iso)
      if (Number.isNaN(d.getTime())) return iso
      return d.toLocaleDateString(lang === 'de' ? 'de-AT' : 'en-IE', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        ...(opts.withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
      })
    },
    [lang],
  )
}


/**
 * Pick the right field from a payload that carries both languages.
 *
 * The backend sends `label` and `label_de` on statuses, endorsements and the like, because
 * those are business terms with settled Austrian wordings that should not be re-translated
 * in the browser. This is how a view reads them.
 */
export function useBilingual() {
  const { lang } = useLang()
  return useCallback(
    (row: Record<string, unknown> | null | undefined, field: string): string => {
      if (!row) return ''
      if (lang === 'de') {
        const german = row[`${field}_de`]
        if (typeof german === 'string' && german) return german
      }
      const base = row[field]
      return typeof base === 'string' ? base : ''
    },
    [lang],
  )
}


/**
 * The platform's own enum vocabulary, in both languages.
 *
 * These arrive from the API as keys — a decision, a severity, a queue reason — and they end
 * up on chips where a raw `adverse_decision_review` reads as a leak. A bounded table is the
 * right shape for them: the set is small, it is ours, and a missing entry falls back to the
 * key with its underscores opened out rather than to nothing.
 */
const ENUMS: Record<string, [string, string]> = {
  // decisions
  Approved:                      ['Approved', 'Genehmigt'],
  Declined:                      ['Declined', 'Abgelehnt'],
  'Review Required':             ['Review required', 'Prüfung erforderlich'],
  'Request Information':         ['Information requested', 'Unterlagen angefordert'],

  // severity
  simple:                        ['Simple', 'Einfach'],
  complex:                       ['Complex', 'Komplex'],

  // coverage
  covered:                       ['Covered', 'Gedeckt'],
  covered_with_excess:           ['Covered, less the excess', 'Gedeckt, abzüglich Selbstbehalt'],
  excluded:                      ['Excluded', 'Nicht gedeckt'],
  lapsed:                        ['Policy lapsed', 'Polizze erloschen'],
  unknown:                       ['Not established', 'Nicht festgestellt'],

  // repairability
  economically_repairable:       ['Economically repairable', 'Wirtschaftlich reparabel'],
  total_loss:                    ['Total loss', 'Totalschaden'],
  borderline:                    ['Borderline', 'Grenzfall'],

  // estimate band
  within_band:                   ['Within expected band', 'Im erwarteten Rahmen'],
  outside_band:                  ['Outside expected band', 'Außerhalb des erwarteten Rahmens'],

  // queue reasons
  adverse_decision_review:       ['Adverse outcome — needs a person',
                                  'Nachteilige Entscheidung — Mensch erforderlich'],
  agent_requested_review:        ['Automation stopped short',
                                  'Automatisierung nicht abgeschlossen'],
  above_autonomous_ceiling:      ['Above the autonomous ceiling',
                                  'Über der Automatisierungsgrenze'],
  injury_reported:               ['Injury reported', 'Personenschaden gemeldet'],
  fraud_signal_elevated:         ['Elevated risk signal', 'Erhöhtes Risikosignal'],
  coverage_uncertain_or_excluded:['Coverage uncertain or excluded',
                                  'Deckung unklar oder ausgeschlossen'],
  complex_damage:                ['Complex damage', 'Komplexer Schaden'],
  evidence_incomplete:           ['Evidence incomplete', 'Unterlagen unvollständig'],
  blocked_security_review:       ['Held at the gateway', 'Am Gateway gestoppt'],
  straight_through:              ['Finished without a person', 'Ohne Mensch abgeschlossen'],
  awaiting_customer:             ['Waiting on the customer', 'Warten auf den Kunden'],

  // queues
  handler:                       ['Claim handler', 'Sachbearbeiter'],
  claim_handler:                 ['Claim handler', 'Sachbearbeiter'],
  coverage_queue:                ['Coverage', 'Deckungsprüfung'],
  assessment:                    ['Assessment', 'Begutachtung'],
  motor_assessor:                ['Motor assessor', 'Kfz-Sachverständiger'],
  operations:                    ['Operations', 'Betrieb'],
  compliance_ops:                ['Compliance & Operations', 'Compliance & Betrieb'],
  injury:                        ['Bodily injury', 'Personenschaden'],
  siu:                           ['Special investigations', 'Sonderermittlung'],
  security:                      ['Security', 'Sicherheit'],
}

/** Translate one of the platform's own enum values. */
export function useEnum() {
  const { lang } = useLang()
  return useCallback(
    (value: string | null | undefined): string => {
      if (!value) return '—'
      const row = ENUMS[value]
      if (row) return row[lang === 'de' ? 1 : 0]
      return value.replace(/_/g, ' ')
    },
    [lang],
  )
}


/**
 * Why a claim arrived on somebody's desk, in a sentence.
 *
 * Keyed by the routing reason the platform assigns, which is the same key the chip shows.
 * The figures come from the task the caller already holds, so the sentence carries the
 * actual amount rather than a generic one — a handler reading "above the limit" wants to
 * know by how much.
 */
const REASON_DETAIL: Record<string, [string, string]> = {
  awaiting_customer: [
    'Outstanding evidence has been requested from the customer.',
    'Fehlende Unterlagen wurden beim Kunden angefordert.',
  ],
  straight_through: [
    'Every check passed within the autonomous limit.',
    'Alle Prüfungen bestanden, innerhalb der Automatisierungsgrenze.',
  ],
  injury_reported: [
    'Injury reported — automatic settlement stopped and referred to the bodily-injury team.',
    'Personenschaden gemeldet — die automatische Abrechnung wurde gestoppt und der Fall an '
      + 'das Personenschaden-Team übergeben.',
  ],
  fraud_signal_elevated: [
    'Risk score above the autonomy threshold — autonomous progression frozen and the '
      + 'evidence trail preserved.',
    'Der Risikowert liegt über der Automatisierungsschwelle — die automatische Bearbeitung '
      + 'ist gesperrt, die Beweiskette bleibt erhalten.',
  ],
  coverage_uncertain_or_excluded: [
    'The coverage position could not be relied upon automatically — referred to coverage.',
    'Die Deckungslage konnte nicht automatisch beurteilt werden — zur Deckungsprüfung '
      + 'vorgelegt.',
  ],
  adverse_decision_review: [
    'An adverse outcome is never issued automatically — a named person confirms it.',
    'Eine nachteilige Entscheidung wird nie automatisch erlassen — ein benannter '
      + 'Mitarbeiter bestätigt sie.',
  ],
  evidence_incomplete: [
    'Required evidence is incomplete for the decision proposed.',
    'Für die vorgeschlagene Entscheidung fehlen erforderliche Unterlagen.',
  ],
  ceiling_or_severity: [
    '{amount} at severity “{severity}” is outside the autonomous limit.',
    '{amount} bei Schwere „{severity}“ liegt außerhalb der Automatisierungsgrenze.',
  ],
  above_autonomous_ceiling: [
    '{amount} is above the autonomous limit.',
    '{amount} liegt über der Automatisierungsgrenze.',
  ],
  agent_requested_review: [
    'Automation did not reach an outcome it could issue on its own, so a person decides.',
    'Die Automatisierung hat kein Ergebnis erreicht, das sie selbst erlassen darf — ein '
      + 'Mitarbeiter entscheidet.',
  ],
  policy_guard_violation: [
    'One or more checks failed.',
    'Eine oder mehrere Prüfungen sind fehlgeschlagen.',
  ],
}

/** The routing reason as a sentence, with the claim's own figures filled in. */
export function useReasonDetail() {
  const { lang } = useLang()
  const money = useMoney()
  return useCallback(
    (
      reason: string | null | undefined,
      facts: { amount?: number | null; severity?: string | null } = {},
      fallback = '',
    ): string => {
      const row = reason ? REASON_DETAIL[reason] : undefined
      if (!row) return fallback
      return row[lang === 'de' ? 1 : 0]
        .replace('{amount}', money(facts.amount ?? 0))
        .replace('{severity}', facts.severity ?? '—')
    },
    [lang, money],
  )
}
