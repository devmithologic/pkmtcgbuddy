import { useT } from '../i18n/index.jsx'

const DECK_SIZE = 60

// One ViolationCode, two catalogue keys: "3 missing" and "3 too many" are
// different sentences, and no plural rule tells them apart — the choice has to
// be made here, by comparing the same numbers the backend sent.
function violationKey(v) {
  if (v.code === 'wrong_size') {
    return v.params.total < v.params.expected
      ? 'violation.wrong_size_missing'
      : 'violation.wrong_size_excess'
  }
  return `violation.${v.code}`
}

/**
 * The deck's legality state.
 *
 * The validation is computed by the server and arrives already done; this
 * component only presents it. Duplicating the rules on the client to "warn
 * early" would mean having two sources of truth that would eventually
 * disagree.
 */
export default function DeckValidation({ validation, pendingTotal }) {
  const t = useT()

  // `pendingTotal` arrives when there are unsaved changes. In that case the
  // server's validation describes a list that is no longer the one you're
  // looking at, so it can NO LONGER claim "legal deck": that would be a lie
  // on screen.
  //
  // What's shown instead is the total counted on the client — a sum, not a
  // rule — and the verdict is replaced with "unchecked". Recomputing the full
  // rules here would give two sources of truth that would eventually
  // disagree; counting cards runs no such risk.
  const stale = pendingTotal !== null && pendingTotal !== undefined
  const total = stale ? pendingTotal : validation.total_cards
  const isLegal = !stale && validation.is_legal
  const violations = stale ? [] : validation.violations
  const pct = Math.min(100, Math.round((total / DECK_SIZE) * 100))

  return (
    <div className={`validation ${isLegal ? 'is-legal' : ''} ${stale ? 'is-stale' : ''}`}>
      <div className="counter">
        <span className="count">
          {total}
          <span className="of">/{DECK_SIZE}</span>
        </span>
        <span className="verdict">
          {stale
            ? t('deckValidation.unchecked')
            : isLegal
              ? t('deckValidation.legal')
              : t('deckValidation.notLegal')}
        </span>
      </div>

      {/* aria-hidden because the number above already says the same thing to a
          screen reader; the bar is visual reinforcement, not new information. */}
      <div className="bar" aria-hidden="true">
        <div className="bar-fill" style={{ width: `${pct}%` }} />
      </div>

      {violations.length > 0 && (
        <ul className="violations">
          {violations.map((v, i) => (
            <li key={`${v.code}-${i}`}>{t(violationKey(v), v.params)}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
