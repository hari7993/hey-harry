// Hey Harry's WhatsApp link: a linked device on your own WhatsApp that only reads, so she can tell you what a message
// says, where Windows' notifications only say who it's from. It never sends a message, a reaction or a read receipt,
// never shows you online, and takes no old chats when it's linked: only what comes in from then on.
//
//   node bridge.mjs <folder for its keys> [--link]
//
// One JSON object a line on stdout, for whatsapp_link.py:
//   {"type": "qr", "url": "data:image/png;base64,..."}  the code to scan (--link only), a new one every 20 s or so
//   {"type": "open", "me": {"id", "name"}, "linked": true|false}  connected; linked: just now, by a scan
//   {"type": "message", "id", "chat", "chat_pn", "chat_name", "group", "from_me", "sender", "sender_pn",
//    "push_name", "at", "kind", "text"}
//   {"type": "contacts", "contacts": [{"id", "lid", "pn", "name", "notify"}]}
//   {"type": "status", "state": "not_linked" | "closed" | "replaced" | "refused" | "qr_expired", ...}
//   {"type": "logged_out", "code"}  unlinked from the phone: its keys are no good now
// Its stdin closing (Harry quit) ends it, and so do {"cmd": "stop"} and {"cmd": "logout"} (unlink it) a line.
// Without --link and without keys it never makes a code: it says "not_linked" and ends.
import readline from 'node:readline'
import makeWASocket, {
    DisconnectReason, fetchLatestBaileysVersion, getContentType, isJidBroadcast, isJidGroup, isJidNewsletter,
    isJidStatusBroadcast, jidNormalizedUser, normalizeMessageContent, useMultiFileAuthState
} from 'baileys'
import pino from 'pino'
import QRCode from 'qrcode'

const [authDir, ...flags] = process.argv.slice(2)
const LINKING = flags.includes('--link')
const LINK_FOR_MS = 6 * 60 * 1000 // how long new codes keep coming before it gives up
const RETRY_S = [5, 15, 30, 60, 120, 300] // gentle: reconnecting in a tight loop looks like abuse to WhatsApp
const MOST_TEXT = 2000
const started = Date.now()
// what a message says it is: kinds with words, and those said by what they are ("a photo")
const KINDS = {
    conversation: c => ['text', c.conversation],
    extendedTextMessage: c => ['text', c.extendedTextMessage?.text],
    imageMessage: c => ['photo', c.imageMessage?.caption],
    videoMessage: c => [c.videoMessage?.gifPlayback ? 'gif' : 'video', c.videoMessage?.caption],
    ptvMessage: () => ['video note', ''],
    audioMessage: c => [c.audioMessage?.ptt ? 'voice note' : 'audio', ''],
    documentMessage: c => ['document', c.documentMessage?.caption || c.documentMessage?.fileName],
    stickerMessage: () => ['sticker', ''],
    contactMessage: c => ['contact', c.contactMessage?.displayName],
    contactsArrayMessage: c => ['contacts', c.contactsArrayMessage?.displayName],
    locationMessage: c => ['location', c.locationMessage?.name || c.locationMessage?.address],
    liveLocationMessage: () => ['live location', ''],
    pollCreationMessage: c => ['poll', c.pollCreationMessage?.name],
    pollCreationMessageV2: c => ['poll', c.pollCreationMessageV2?.name],
    pollCreationMessageV3: c => ['poll', c.pollCreationMessageV3?.name],
    eventMessage: c => ['event', c.eventMessage?.name],
    buttonsResponseMessage: c => ['text', c.buttonsResponseMessage?.selectedDisplayText],
    listResponseMessage: c => ['text', c.listResponseMessage?.title],
    templateButtonReplyMessage: c => ['text', c.templateButtonReplyMessage?.selectedDisplayText],
}

const logger = pino({ level: process.env.HEYHARRY_WA_LOG || 'warn' }, pino.destination({ dest: 2, sync: true }))
let sock = null
let stopping = false
let everOpened = false
let retries = 0
const groupNames = new Map() // group id: its subject, '' once it couldn't be read

function emit(obj) {
    process.stdout.write(JSON.stringify(obj) + '\n')
}

function stop(code = 0) {
    if (stopping) return
    stopping = true
    try { sock?.end(undefined) } catch { /* already closed */ }
    process.stdout.write('', () => process.exit(code))
    setTimeout(() => process.exit(code), 2000).unref()
}

function number(ts) {
    if (ts && typeof ts === 'object' && typeof ts.toNumber === 'function') return ts.toNumber()
    return Number(ts) || 0
}

function words(text) {
    const t = String(text || '').trim()
    return t.length > MOST_TEXT ? t.slice(0, MOST_TEXT) + '\u2026' : t
}

async function groupName(jid) {
    if (groupNames.has(jid)) return groupNames.get(jid)
    groupNames.set(jid, '') // asked once, even if it can't be read
    try {
        const meta = await sock.groupMetadata(jid)
        groupNames.set(jid, meta?.subject || '')
    } catch (err) {
        logger.warn({ err: String(err) }, 'group name')
    }
    return groupNames.get(jid)
}

async function onMessage(m) {
    const key = m?.key || {}
    const chat = key.remoteJid || ''
    if (!chat || isJidStatusBroadcast(chat) || isJidNewsletter(chat) || isJidBroadcast(chat)) return
    const content = normalizeMessageContent(m.message)
    const type = getContentType(content)
    const read = KINDS[type]
    if (!read) return // reactions, edits, deletions, keys and the rest: nothing to tell you
    const [kind, text] = read(content)
    const group = Boolean(isJidGroup(chat))
    const out = {
        type: 'message', id: key.id || '', chat, chat_pn: group ? '' : (key.remoteJidAlt || ''),
        chat_name: group ? await groupName(chat) : '', group, from_me: Boolean(key.fromMe),
        sender: key.fromMe ? 'me' : (group ? (key.participant || '') : chat),
        sender_pn: group ? (key.participantAlt || '') : (key.remoteJidAlt || ''),
        push_name: m.pushName || '', at: number(m.messageTimestamp) || Math.floor(Date.now() / 1000),
        kind, text: words(text),
    }
    emit(out)
}

function onContacts(list) {
    const contacts = (list || []).filter(c => c?.id && (c.name || c.notify || c.verifiedName)).map(c => ({
        id: c.id, lid: c.lid || '', pn: c.phoneNumber || '', name: c.name || '', notify: c.notify || c.verifiedName || ''
    }))
    if (contacts.length) emit({ type: 'contacts', contacts })
}

async function latest() {
    // WhatsApp turns away an old version of its web app: the newest one Baileys knows of, else its own
    try {
        const got = await Promise.race([fetchLatestBaileysVersion(),
            new Promise(resolve => setTimeout(() => resolve({}), 8000))])
        return got?.version
    } catch {
        return undefined
    }
}

async function onConnection({ connection, lastDisconnect, qr }) {
    if (qr) {
        if (!LINKING) { // its keys are gone: never a code nobody asked for
            emit({ type: 'status', state: 'not_linked' })
            return stop(0)
        }
        emit({ type: 'qr', url: await QRCode.toDataURL(qr, { margin: 2, scale: 8 }) })
    }
    if (connection === 'open') {
        retries = 0
        const me = sock.user || {}
        emit({ type: 'open', me: { id: me.id ? jidNormalizedUser(me.id) : '', name: me.name || me.notify || '' },
               linked: LINKING && !everOpened })
        everOpened = true
    }
    if (connection !== 'close' || stopping) return
    const code = lastDisconnect?.error?.output?.statusCode
    const why = String(lastDisconnect?.error?.message || '')
    if (code === DisconnectReason.loggedOut || code === DisconnectReason.badSession) {
        emit({ type: 'logged_out', code })
        return stop(0)
    }
    if (code === DisconnectReason.connectionReplaced) { // another copy with the same keys: never fight it
        emit({ type: 'status', state: 'replaced' })
        return stop(0)
    }
    if (code === DisconnectReason.forbidden || code === DisconnectReason.multideviceMismatch) {
        emit({ type: 'status', state: 'refused', code, why })
        return stop(3)
    }
    if (code === DisconnectReason.restartRequired) return connect() // what WhatsApp asks for right after the scan
    if (LINKING && !everOpened) { // the codes ran out unscanned: new ones, for a while
        if (Date.now() - started > LINK_FOR_MS) {
            emit({ type: 'status', state: 'qr_expired' })
            return stop(0)
        }
        return setTimeout(connect, 1000)
    }
    const wait = RETRY_S[Math.min(retries, RETRY_S.length - 1)]
    retries += 1
    emit({ type: 'status', state: 'closed', code: code ?? null, why, retry_in: wait })
    setTimeout(connect, wait * 1000)
}

async function connect() {
    if (stopping) return
    const { state, saveCreds } = await useMultiFileAuthState(authDir)
    if (!state.creds.me && !LINKING) {
        emit({ type: 'status', state: 'not_linked' })
        return stop(0)
    }
    sock = makeWASocket({
        auth: state, version: await latest(), logger, browser: ['Hey Harry', 'Chrome', '1.0.0'],
        markOnlineOnConnect: false, // you stay as you are, and your phone still rings for messages
        syncFullHistory: false, shouldSyncHistoryMessage: () => false, // no old chats, only what comes in now
        generateHighQualityLinkPreview: false, getMessage: async () => undefined,
    })
    sock.ev.on('creds.update', saveCreds)
    sock.ev.on('connection.update', update => onConnection(update).catch(err => logger.error({ err: String(err) })))
    sock.ev.on('messages.upsert', ({ messages, type }) => {
        if (type !== 'notify') return // new ones only, not what another device of yours synced
        for (const m of messages || []) onMessage(m).catch(err => logger.error({ err: String(err) }, 'message'))
    })
    sock.ev.on('contacts.upsert', onContacts)
    sock.ev.on('contacts.update', onContacts)
    sock.ev.on('groups.update', groups => {
        for (const g of groups || []) if (g?.id && g.subject) groupNames.set(g.id, g.subject)
    })
}

if (!authDir) {
    process.stderr.write('usage: node bridge.mjs <folder for its keys> [--link]\n')
    process.exit(2)
}
process.on('unhandledRejection', err => logger.error({ err: String(err) }, 'unhandled'))
const commands = readline.createInterface({ input: process.stdin })
commands.on('line', async line => {
    let cmd = {}
    try { cmd = JSON.parse(line) } catch { return }
    if (cmd.cmd === 'stop') return stop(0)
    if (cmd.cmd === 'logout' && sock) {
        try { await sock.logout() } catch (err) { logger.warn({ err: String(err) }, 'logout') }
        emit({ type: 'logged_out', code: DisconnectReason.loggedOut })
        return stop(0)
    }
})
commands.on('close', () => stop(0)) // Harry quit, or was ended: so does this
connect().catch(err => {
    logger.error({ err: String(err) }, 'connect')
    emit({ type: 'status', state: 'closed', why: String(err), retry_in: null })
    stop(1)
})
