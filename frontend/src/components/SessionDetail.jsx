import { useEffect, useState } from 'react'
import { listDecks } from '../api/decks'
import {
  addMatch,
  deleteMatch,
  getSession,
  listTags,
  updateMatch,
  updateSession,
} from '../api/sessions'
import { SESSION_TYPES } from '../sessionTypes'
import PokemonPair from './PokemonPair'
import TagInput from './TagInput'
import PokemonPicker from './PokemonPicker'
import { useT } from '../i18n/index.jsx'

// A match result, in wire form. Its label depends on the active locale (see
// sessionTypes.js for the same reasoning), so only the value is a module
// constant; the label is looked up at render time as `sessionDetail.result<Value>`.
const RESULTS = ['win', 'loss', 'tie']

function resultKey(value) {
  return `sessionDetail.result${value[0].toUpperCase()}${value.slice(1)}`
}

const EMPTY_ROUND = {
  opponent_archetype: '',
  result: 'win',
  notes: '',
  opponent_primary: null,
  opponent_secondary: null,
}

/**
 * An open session: header, record, rounds, and the form to add the next
 * one.
 *
 * The record is NOT computed here. Every operation on a round returns the
 * whole session already recalculated by the server, so there's only one
 * implementation of the calculation and there can't be two that disagree.
 */
/**
 * The header's editable fields, derived from a session.
 *
 * Takes the session as an argument instead of reading state because it
 * needs to be called at two different moments: on clicking "edit session",
 * when the state is already set, and right when the server's response
 * arrives, when it isn't yet.
 */
function headerFrom(s) {
  return {
    name: s.name ?? '',
    played_at: s.played_at,
    session_type: s.session_type,
    notes: s.notes ?? '',
    deck_version_id: s.deck_version_id,
    tags: s.tags ?? [],
  }
}

export default function SessionDetail({ sessionId, startEditing = false, onBack }) {
  const t = useT()
  const [session, setSession] = useState(null)
  const [form, setForm] = useState(EMPTY_ROUND)
  // Which ROUND is being corrected, or null. Named explicitly so it isn't
  // confused with editingHeader, which is a different thing.
  const [editingRound, setEditingRound] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  // HEADER editing. Rounds don't go through here: each one is saved as
  // it's added, so there's no pending state to confirm. This exists
  // because until now the session was frozen once created, and getting the
  // date or the deck wrong had no fix.
  const [editingHeader, setEditingHeader] = useState(false)
  const [header, setHeader] = useState(null)
  const [decks, setDecks] = useState([])
  const [allTags, setAllTags] = useState([])

  useEffect(() => {
    let active = true

    getSession(sessionId)
      .then((s) => {
        if (!active) return
        setSession(s)

        // Opens already editing, when arriving from the list's pencil icon.
        //
        // This has to happen HERE and not in editingHeader's useState: the
        // form is filled from the session, and on mount the session is
        // still null. Seeding it earlier would throw a TypeError on
        // header.played_at on the first render. It's seeded with `s`, the
        // data that just arrived, not with the `session` state, which
        // hasn't been updated yet in this same pass.
        if (startEditing) {
          setHeader(headerFrom(s))
          setEditingHeader(true)
        }
      })
      .catch((err) => active && setError(err.message))

    return () => {
      active = false
    }
  }, [sessionId, startEditing])

  // The decks are needed to be able to correct which one was played.
  useEffect(() => {
    let active = true
    Promise.all([listDecks(), listTags()])
      .then(([d, tagList]) => {
        if (!active) return
        setDecks(d)
        setAllTags(tagList)
      })
      .catch(() => {})
    return () => {
      active = false
    }
  }, [])

  function startEditHeader() {
    setHeader(headerFrom(session))
    setEditingHeader(true)
  }

  async function saveHeader(event) {
    event.preventDefault()
    const ok = await mutate(() =>
      updateSession(sessionId, {
        ...header,
        name: header.name.trim() || null,
        notes: header.notes.trim() || null,
      }),
    )
    if (ok) setEditingHeader(false)
  }

  /** Common wrapper: every mutation returns the whole session and replaces it. */
  async function mutate(operation) {
    setBusy(true)
    setError(null)
    try {
      setSession(await operation())
      return true
    } catch (err) {
      setError(err.message)
      return false
    } finally {
      setBusy(false)
    }
  }

  async function handleAdd(event) {
    event.preventDefault()
    const payload = { ...form, notes: form.notes.trim() || null }

    const ok = await mutate(() =>
      editingRound === null
        ? addMatch(sessionId, payload)
        : updateMatch(sessionId, editingRound, payload),
    )

    if (ok) {
      setForm(EMPTY_ROUND)
      setEditingRound(null)
    }
  }

  function startEdit(match) {
    setEditingRound(match.round)
    setForm({
      opponent_archetype: match.opponent_archetype,
      result: match.result,
      notes: match.notes ?? '',
      opponent_primary: match.opponent_primary ?? null,
      opponent_secondary: match.opponent_secondary ?? null,
    })
  }

  function cancelEdit() {
    setEditingRound(null)
    setForm(EMPTY_ROUND)
  }

  if (error && !session) return <p className="error">{error}</p>
  if (!session) return <p>{t('common.loading')}</p>

  const { record } = session

  return (
    <div className="session-detail">
      <div className="builder-head">
        <button type="button" className="back" onClick={onBack}>
          {t('sessionDetail.back')}
        </button>
        <div className="session-head">
          <h2>{session.name || t(`sessionType.${session.session_type}`)}</h2>
          <p className="subtitle">
            {session.played_at} · {t(`sessionType.${session.session_type}`)} · {session.deck_name}{' '}
            <span className="vtag">v{session.deck_version}</span>
          </p>
          {session.tags?.length > 0 && (
            <span className="tag-chips read-only">
              {session.tags.map((tag) => (
                <span key={tag} className="tag-chip">
                  {tag}
                </span>
              ))}
            </span>
          )}
          {session.notes && <p className="session-notes">{session.notes}</p>}
          {!editingHeader && (
            <button type="button" className="peek" onClick={startEditHeader}>
              {t('sessionDetail.editSession')}
            </button>
          )}
        </div>
      </div>

      {editingHeader && (
        <form onSubmit={saveHeader} className="match-form session-edit">
          <h3>{t('sessionDetail.editSessionHeading')}</h3>

          <label>
            {t('sessionDetail.labelDate')}
            <input
              type="date"
              value={header.played_at}
              onChange={(e) => setHeader({ ...header, played_at: e.target.value })}
              required
            />
          </label>

          <label>
            {t('sessionDetail.labelType')}
            <select
              value={header.session_type}
              onChange={(e) => setHeader({ ...header, session_type: e.target.value })}
            >
              {SESSION_TYPES.map((value) => (
                <option key={value} value={value}>
                  {t(`sessionType.${value}`)}
                </option>
              ))}
            </select>
          </label>

          <label>
            {t('sessionDetail.labelDeck')}
            <select
              value={header.deck_version_id}
              onChange={(e) => setHeader({ ...header, deck_version_id: e.target.value })}
            >
              {/* The session's current version may not be the deck's
                  current version — you played with v1 and today you're on
                  v3 — so it's offered explicitly so it isn't lost when the
                  dropdown opens. */}
              <option value={session.deck_version_id}>
                {session.deck_name} (v{session.deck_version}) — {t('sessionDetail.deckCurrent')}
              </option>
              {decks
                .filter((d) => d.current_version_id !== session.deck_version_id)
                .map((d) => (
                  <option key={d.id} value={d.current_version_id}>
                    {d.name} (v{d.current_version})
                  </option>
                ))}
            </select>
          </label>

          <label>
            {t('sessionDetail.labelName')} <span className="optional">{t('common.optional')}</span>
            <input
              type="text"
              value={header.name}
              onChange={(e) => setHeader({ ...header, name: e.target.value })}
              placeholder={t('sessionDetail.placeholderName')}
            />
          </label>

          <label>
            {t('sessionDetail.labelTags')} <span className="optional">{t('common.optional')}</span>
            <TagInput
              value={header.tags}
              suggestions={allTags}
              onChange={(newTags) => setHeader({ ...header, tags: newTags })}
            />
          </label>

          <label>
            {t('sessionDetail.labelEventNotes')} <span className="optional">{t('common.optional')}</span>
            <textarea
              value={header.notes}
              onChange={(e) => setHeader({ ...header, notes: e.target.value })}
              rows={2}
              placeholder={t('sessionDetail.placeholderEventNotes')}
            />
          </label>

          <div className="round-form-actions">
            <button type="submit" disabled={busy}>
              {busy ? t('sessionDetail.saving') : t('sessionDetail.saveSession')}
            </button>
            <button type="button" className="secondary" onClick={() => setEditingHeader(false)}>
              {t('common.cancel')}
            </button>
          </div>
        </form>
      )}

      {/* Rounds on the left, the form for the next one on the right.
          Before, the form went below the list, so in a five-round
          tournament you had to scroll all the way down to log the sixth. */}
      <div className="screen-split screen-split--end">
      <div className="pane">
      <div className="record">
        <span className="record-figure">
          {record.wins}–{record.losses}–{record.ties}
        </span>
        <span className="record-label">
          {session.matches.length === 0
            ? t('sessionDetail.noRounds')
            : t('sessionDetail.recordLabel', { count: session.matches.length })}
        </span>
      </div>

      {error && <p className="error">{error}</p>}

      <ol className="rounds">
        {session.matches.map((m) => (
          <li key={m.round} className={`round round--${m.result}`}>
            <span className="round-no">R{m.round}</span>
            <span className="round-arch">
              {/* Fixed lane: an opponent can have two icons, one, or none,
                  and without it the deck names don't start aligned. */}
              <span className="pkm-slot">
                <PokemonPair
                  primary={m.opponent_primary}
                  secondary={m.opponent_secondary}
                  size={26}
                />
              </span>
              {m.opponent_archetype}
            </span>
            <span className="round-result">
              {t(resultKey(m.result))}
            </span>
            <span className="round-actions">
              <button type="button" onClick={() => startEdit(m)} disabled={busy}>
                {t('sessionDetail.editRound')}
              </button>
              <button
                type="button"
                onClick={() => {
                  // Cancel the correction in progress BEFORE deleting. The
                  // server renumbers the rounds on delete, so an open
                  // editingRound=2 would end up pointing at a different
                  // round, and saving would overwrite the wrong one with no
                  // visible error. Silent corruption.
                  cancelEdit()
                  mutate(() => deleteMatch(sessionId, m.round))
                }}
                disabled={busy}
              >
                {t('sessionDetail.deleteRound')}
              </button>
            </span>
            {m.notes && <p className="round-notes">{m.notes}</p>}
          </li>
        ))}
      </ol>
      </div>

      <form onSubmit={handleAdd} className="match-form round-form">
        <h3>
          {editingRound === null
            ? t('sessionDetail.roundHeading', { round: session.matches.length + 1 })
            : t('sessionDetail.editRoundHeading', { round: editingRound })}
        </h3>

        <label>
          {t('sessionDetail.labelOpponentDeck')}
          <input
            type="text"
            value={form.opponent_archetype}
            onChange={(e) => setForm({ ...form, opponent_archetype: e.target.value })}
            placeholder={t('sessionDetail.placeholderOpponentDeck')}
            required
          />
        </label>

        <label>
          {t('sessionDetail.labelOpponentPokemon')} <span className="optional">{t('common.optional')}</span>
          <span className="pkm-two">
            <PokemonPicker
              value={form.opponent_primary}
              onSelect={(p) => setForm({ ...form, opponent_primary: p })}
              placeholder={t('sessionDetail.placeholderOpponentPrimaryPokemon')}
            />
            <PokemonPicker
              value={form.opponent_secondary}
              onSelect={(p) => setForm({ ...form, opponent_secondary: p })}
              placeholder={t('sessionDetail.placeholderOpponentSecondaryPokemon')}
            />
          </span>
        </label>

        <label>
          {t('sessionDetail.labelResult')}
          <select
            value={form.result}
            onChange={(e) => setForm({ ...form, result: e.target.value })}
          >
            {RESULTS.map((value) => (
              <option key={value} value={value}>
                {t(resultKey(value))}
              </option>
            ))}
          </select>
        </label>

        <label>
          {t('sessionDetail.labelNotes')} <span className="optional">{t('common.optional')}</span>
          <textarea
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            rows={2}
            placeholder={t('sessionDetail.placeholderNotes')}
          />
        </label>

        <div className="round-form-actions">
          <button type="submit" disabled={busy}>
            {editingRound === null ? t('sessionDetail.addRound') : t('sessionDetail.saveCorrection')}
          </button>
          {editingRound !== null && (
            <button type="button" className="secondary" onClick={cancelEdit}>
              {t('common.cancel')}
            </button>
          )}
        </div>
      </form>
      </div>
    </div>
  )
}
