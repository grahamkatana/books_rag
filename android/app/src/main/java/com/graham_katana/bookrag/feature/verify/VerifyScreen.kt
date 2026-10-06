package com.graham_katana.bookrag.feature.verify

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.graham_katana.bookrag.core.ui.plainTextButton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private const val DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
// ponytail: the file is held in memory to send it; a streamed request body if drafts ever get this big.
private const val MAX_DOCX_BYTES = 25L * 1024 * 1024
/** Mirrors the API's MAX_VERIFICATION_TEXT_CHARS default. */
private const val MAX_TEXT_CHARS = 20_000

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VerifyScreen(viewModel: VerifyViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var pasting by rememberSaveable { mutableStateOf(false) }
    var deleting by remember { mutableStateOf<VerificationDocument?>(null) }
    var localError by remember { mutableStateOf<String?>(null) }

    // The system file picker: no storage permission needed, and it only offers Word documents (all the API accepts).
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri != null) scope.launch {
            val name = displayName(context, uri)
            val bytes = withContext(Dispatchers.IO) { readFile(context, uri) }
            when {
                !name.endsWith(".docx", ignoreCase = true) -> localError = "Only Word documents (.docx) can be verified."
                bytes == null -> localError = "That file could not be read, or is larger than 25 MB."
                else -> { localError = null; viewModel.upload(name, bytes) }
            }
        }
    }
    val pickFile = { picker.launch(arrayOf(DOCX_MIME)) }
    val open = state.open

    BackHandler(enabled = open != null, onBack = viewModel::close)

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(open?.filename ?: "Verify", maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = { if (open != null) IconButton(onClick = viewModel::close) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back to documents") } },
                actions = {
                    if (open == null) {
                        IconButton(onClick = { pasting = true }, enabled = !state.isSubmitting) { Icon(Icons.Default.Edit, "Verify pasted text") }
                        IconButton(onClick = pickFile, enabled = !state.isSubmitting) { Icon(Icons.Default.Add, "Upload a Word document") }
                    } else {
                        DocumentMenu(open, busy = state.awaitingCrossCheck.isNotEmpty(), onRerun = viewModel::rerun, onCrossCheck = viewModel::crossCheck, onDelete = { deleting = open })
                    }
                },
            )
        },
        // The screen sits inside the app's own frame, which has already made room for the system bars.
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
    ) { padding ->
        Column(Modifier.padding(padding).fillMaxSize()) {
            (localError ?: state.error)?.let { message ->
                Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(message, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
                    TextButton(onClick = { localError = null; viewModel.dismissError() }, colors = plainTextButton()) { Text("Dismiss") }
                }
            }
            if (state.isSubmitting) {
                Text("Sending your draft…", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall, modifier = Modifier.padding(horizontal = 16.dp))
                LinearProgressIndicator(Modifier.fillMaxWidth().padding(16.dp))
            }
            if (open == null) DocumentList(state, onOpen = viewModel::open, onDelete = { deleting = it }, onUpload = pickFile, onPaste = { pasting = true })
            else DocumentDetail(open, state, onClaim = viewModel::openClaim)
        }
    }

    if (pasting) PasteDialog(onDismiss = { pasting = false }, onSubmit = { text, title -> pasting = false; viewModel.submitText(text, title) })

    deleting?.let { document ->
        AlertDialog(
            onDismissRequest = { deleting = null },
            title = { Text("Delete this document?") },
            text = { Text("“${document.filename}” and its verdicts will be removed. This cannot be undone.") },
            confirmButton = { TextButton(onClick = { viewModel.delete(document.id); deleting = null }, colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error)) { Text("Delete") } },
            dismissButton = { TextButton(onClick = { deleting = null }, colors = plainTextButton()) { Text("Cancel") } },
        )
    }

    state.openClaim?.let { claim ->
        ModalBottomSheet(onDismissRequest = viewModel::closeClaim) { ClaimSheet(claim) }
    }
}

@Composable
private fun DocumentMenu(document: VerificationDocument, busy: Boolean, onRerun: (Boolean) -> Unit, onCrossCheck: () -> Unit, onDelete: () -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    fun pick(action: () -> Unit) { expanded = false; action() }
    Box {
        IconButton(onClick = { expanded = true }) { Icon(Icons.Default.MoreVert, "Document actions") }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            // Nothing can be re-run or reviewed while the first pass, or a second opinion, is still under way.
            val idle = document.isFinished && !busy
            DropdownMenuItem(text = { Text("Find the claims again and verify") }, enabled = idle, onClick = { pick { onRerun(true) } })
            DropdownMenuItem(text = { Text("Verify the same claims again") }, enabled = idle && document.claims.isNotEmpty(), onClick = { pick { onRerun(false) } })
            DropdownMenuItem(text = { Text("Get a second opinion") }, enabled = idle && document.status == "done", onClick = { pick(onCrossCheck) })
            HorizontalDivider()
            DropdownMenuItem(text = { Text("Delete", color = MaterialTheme.colorScheme.error) }, onClick = { pick(onDelete) })
        }
    }
}

@Composable
private fun DocumentList(state: VerifyUiState, onOpen: (VerificationDocument) -> Unit, onDelete: (VerificationDocument) -> Unit, onUpload: () -> Unit, onPaste: () -> Unit) {
    when {
        state.isLoading -> Text("Loading documents…", color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(16.dp))
        state.documents.isEmpty() -> Column(Modifier.fillMaxSize().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
            Text("Check a draft against your library", style = MaterialTheme.typography.titleMedium)
            Text("Each factual claim is found, checked, and given a verdict with the evidence behind it.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 4.dp, bottom = 20.dp))
            Button(onClick = onUpload, enabled = !state.isSubmitting, modifier = Modifier.fillMaxWidth()) { Text("Upload a Word document") }
            OutlinedButton(onClick = onPaste, enabled = !state.isSubmitting, colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.onSurface), modifier = Modifier.fillMaxWidth().padding(top = 8.dp)) { Text("Paste text instead") }
        }
        else -> LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(state.documents, key = VerificationDocument::id) { document ->
                Row(
                    Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, RoundedCornerShape(12.dp)).clickable { onOpen(document) }.padding(start = 14.dp, top = 10.dp, bottom = 10.dp, end = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(document.filename, style = MaterialTheme.typography.bodyMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        val status = when (document.status) {
                            "done" -> "${document.claimCount} ${if (document.claimCount == 1) "claim" else "claims"} checked"
                            "failed" -> "Failed"
                            else -> "Verifying…"
                        }
                        Text(status, style = MaterialTheme.typography.bodySmall, color = if (document.status == "failed") MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    IconButton(onClick = { onDelete(document) }) { Icon(Icons.Default.Delete, "Delete ${document.filename}", tint = MaterialTheme.colorScheme.onSurfaceVariant) }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DocumentDetail(document: VerificationDocument, state: VerifyUiState, onClaim: (Claim) -> Unit) {
    val claims = remember(document.claims) { document.claims.sortedBy(Claim::orderIndex) }
    val verified = claims.count { it.verification != null }
    LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item(key = "status") {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                when {
                    state.isLoadingOpen -> Text("Loading…", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    document.status == "failed" -> Text(document.errorMessage ?: "Verification failed. Try running it again from the menu.", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
                    !document.isFinished -> {
                        Text(if (claims.isEmpty()) "Reading the draft and finding its claims…" else "Verifying: $verified of ${claims.size} claims checked", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
                        if (claims.isEmpty()) LinearProgressIndicator(Modifier.fillMaxWidth()) else LinearProgressIndicator(progress = { verified.toFloat() / claims.size }, modifier = Modifier.fillMaxWidth())
                        Text("This usually takes a few minutes. You can leave this screen; it carries on.", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
                    }
                    claims.isEmpty() -> Text("No checkable claims were found in this draft.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    else -> FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        // The tally, in the order that matters most to someone fixing a draft.
                        VERDICT_ORDER.forEach { verdict ->
                            val count = claims.count { it.verification?.verdict == verdict }
                            if (count > 0) VerdictBadge(verdict, suffix = " · $count")
                        }
                    }
                }
                if (state.awaitingCrossCheck.isNotEmpty()) {
                    Text("Getting a second opinion on ${state.awaitingCrossCheck.size} ${if (state.awaitingCrossCheck.size == 1) "claim" else "claims"}…", color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
                    LinearProgressIndicator(Modifier.fillMaxWidth())
                }
            }
        }
        items(claims, key = Claim::id) { claim ->
            Column(
                Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, RoundedCornerShape(12.dp)).clickable { onClaim(claim) }.padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(claim.text, style = MaterialTheme.typography.bodyMedium, maxLines = 4, overflow = TextOverflow.Ellipsis)
                val verification = claim.verification
                if (verification == null) Text("Waiting to be checked…", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                else Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    VerdictBadge(verification.verdict)
                    verification.crossCheck?.let {
                        Text(if (it.agrees) "Second opinion agrees" else "Second opinion disagrees", style = MaterialTheme.typography.bodySmall, color = if (it.agrees) MaterialTheme.colorScheme.onSurfaceVariant else verdictColor("partially_supported"))
                    }
                }
            }
        }
    }
}

@Composable
private fun ClaimSheet(claim: Claim) {
    val uriHandler = LocalUriHandler.current
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 28.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Claim", style = MaterialTheme.typography.titleMedium)
        SelectionContainer { Text(claim.text, style = MaterialTheme.typography.bodyMedium, fontStyle = FontStyle.Italic) }

        val verification = claim.verification
        if (verification == null) {
            Text("Waiting to be checked…", color = muted, style = MaterialTheme.typography.bodyMedium)
            return@Column
        }
        VerdictBadge(verification.verdict, confidence = verification.confidence)
        SelectionContainer { Text(verification.explanation, style = MaterialTheme.typography.bodyMedium, color = muted) }

        if (verification.evidence.isNotEmpty()) {
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            Text("EVIDENCE", style = MaterialTheme.typography.labelSmall, color = muted)
            verification.evidence.forEach { evidence ->
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    listOfNotNull(evidence.title, evidence.locator).takeIf { it.isNotEmpty() }?.let { Text(it.joinToString(", "), style = MaterialTheme.typography.bodyMedium) }
                    evidence.webUrl?.let { url ->
                        Text(url, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.clickable { runCatching { uriHandler.openUri(url) } })
                    }
                    SelectionContainer { Text(evidence.excerpt, style = MaterialTheme.typography.bodySmall, color = muted) }
                }
            }
        }

        verification.crossCheck?.let { second ->
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
            Text("SECOND OPINION" + if (second.model.isNotBlank()) " (${second.model})" else "", style = MaterialTheme.typography.labelSmall, color = muted)
            Text(if (second.agrees) "Agrees. Its own verdict:" else "Disagrees. Its own verdict:", style = MaterialTheme.typography.bodyMedium, color = if (second.agrees) verdictColor("supported") else verdictColor("partially_supported"))
            VerdictBadge(second.verdict, confidence = second.confidence)
            SelectionContainer { Text(second.explanation, style = MaterialTheme.typography.bodyMedium, color = muted) }
            if (!second.isCheckableClaim) Text("The second model judges that this is not a claim that can be checked against outside sources at all.", style = MaterialTheme.typography.bodySmall, color = verdictColor("partially_supported"))
        }
    }
}

@Composable
private fun PasteDialog(onDismiss: () -> Unit, onSubmit: (String, String) -> Unit) {
    var title by rememberSaveable { mutableStateOf("") }
    var text by rememberSaveable { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Verify pasted text") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(value = title, onValueChange = { title = it.take(120) }, label = { Text("Title (optional)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(value = text, onValueChange = { text = it.take(MAX_TEXT_CHARS) }, label = { Text("Text to check") }, modifier = Modifier.fillMaxWidth().heightIn(min = 140.dp, max = 260.dp))
                Text("%,d / %,d characters".format(text.length, MAX_TEXT_CHARS), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        },
        confirmButton = { TextButton(onClick = { onSubmit(text, title) }, enabled = text.isNotBlank()) { Text("Verify") } },
        dismissButton = { TextButton(onClick = onDismiss, colors = plainTextButton()) { Text("Cancel") } },
    )
}

// ---- verdicts ----

/** Worst first: what someone fixing a draft needs to look at soonest. */
private val VERDICT_ORDER = listOf("contradicted", "error", "partially_supported", "unverifiable", "supported")

private fun verdictLabel(verdict: String) = when (verdict) {
    "supported" -> "Supported"
    "partially_supported" -> "Partially supported"
    "contradicted" -> "Contradicted"
    "error" -> "Check failed" // the check itself broke; not the same as looking and finding nothing
    else -> "Unverifiable"
}

/** Green only for a clear yes, amber for the real middle category, red for what needs attention, grey for no evidence either way. */
@Composable
private fun verdictColor(verdict: String): Color {
    val dark = isSystemInDarkTheme()
    return when (verdict) {
        "supported" -> if (dark) Color(0xFF4ADE80) else Color(0xFF15803D)
        "partially_supported" -> if (dark) Color(0xFFFBBF24) else Color(0xFFB45309)
        "contradicted", "error" -> if (dark) Color(0xFFF87171) else Color(0xFFB91C1C)
        else -> MaterialTheme.colorScheme.onSurfaceVariant
    }
}

@Composable
private fun VerdictBadge(verdict: String, suffix: String = "", confidence: String? = null) {
    val color = verdictColor(verdict)
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(verdictLabel(verdict) + suffix, style = MaterialTheme.typography.labelMedium, color = color, modifier = Modifier.background(color.copy(alpha = 0.12f), RoundedCornerShape(6.dp)).padding(horizontal = 8.dp, vertical = 3.dp))
        confidence?.let { Text("${it.replaceFirstChar(Char::uppercase)} confidence", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}

// ---- reading the picked file ----

private fun displayName(context: Context, uri: Uri): String =
    context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
        if (cursor.moveToFirst()) cursor.getString(0) else null
    } ?: "document.docx"

/** Null when the file cannot be read or is over the limit. Blocking: call from IO. */
private fun readFile(context: Context, uri: Uri): ByteArray? = try {
    context.contentResolver.openInputStream(uri)?.use { input ->
        val out = java.io.ByteArrayOutputStream()
        val buffer = ByteArray(64 * 1024)
        while (out.size() <= MAX_DOCX_BYTES) {
            val n = input.read(buffer)
            if (n < 0) return@use out.toByteArray()
            out.write(buffer, 0, n)
        }
        null
    }
} catch (e: Exception) {
    null
}
