package com.graham_katana.bookrag.feature.chat

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DrawerValue
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.ModalDrawerSheet
import androidx.compose.material3.ModalNavigationDrawer
import androidx.compose.material3.NavigationDrawerItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.rememberDrawerState
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.graham_katana.bookrag.core.ui.MarkdownText
import com.graham_katana.bookrag.core.ui.plainTextButton
import com.graham_katana.bookrag.feature.library.Book
import com.graham_katana.bookrag.feature.library.LibraryItem
import com.graham_katana.bookrag.feature.library.Paper
import kotlinx.coroutines.launch

private val SUGGESTIONS = listOf(
    "How is technology acceptance defined across my sources?",
    "What are the main criticisms of the Technology Acceptance Model?",
    "Which research designs suit a qualitative case study, and why?",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(viewModel: ChatViewModel, email: String, onLogout: () -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val drawer = rememberDrawerState(DrawerValue.Closed)
    val scope = rememberCoroutineScope()
    val listState = rememberLazyListState()
    var draft by rememberSaveable { mutableStateOf("") }
    var pickingSources by remember { mutableStateOf(false) }
    var deleting by remember { mutableStateOf<ChatSummary?>(null) }

    // Follow the answer as it streams in.
    LaunchedEffect(state.messages.size, state.messages.lastOrNull()?.text?.length) {
        if (state.messages.isNotEmpty()) listState.scrollToItem(state.messages.lastIndex)
    }

    val canSend = draft.isNotBlank() && !state.isStreaming && !state.isLoadingChat
    val send = { if (canSend) { viewModel.send(draft); draft = "" } }

    ModalNavigationDrawer(
        drawerState = drawer,
        drawerContent = {
            ModalDrawerSheet {
                Column(Modifier.fillMaxSize().padding(vertical = 12.dp)) {
                    Text("Book RAG", style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(horizontal = 24.dp, vertical = 8.dp))
                    OutlinedButton(
                        onClick = { viewModel.newChat(); scope.launch { drawer.close() } },
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.onSurface),
                        modifier = Modifier.padding(horizontal = 16.dp).fillMaxWidth(),
                    ) { Icon(Icons.Default.Add, null); Text("  New chat") }
                    Text("Chats", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(start = 24.dp, top = 16.dp, bottom = 4.dp))
                    LazyColumn(Modifier.weight(1f).padding(horizontal = 12.dp)) {
                        items(state.chats, key = { it.id }) { chat ->
                            NavigationDrawerItem(
                                label = { Text(chat.title ?: "Untitled chat", maxLines = 1, overflow = TextOverflow.Ellipsis) },
                                selected = chat.id == state.chatId,
                                onClick = { viewModel.openChat(chat.id); scope.launch { drawer.close() } },
                                badge = { IconButton(onClick = { deleting = chat }) { Icon(Icons.Default.Delete, "Delete chat", tint = MaterialTheme.colorScheme.onSurfaceVariant) } },
                            )
                        }
                        if (state.chats.isEmpty()) item { Text("Your chats will appear here.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(12.dp)) }
                    }
                    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                    Text(email, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(start = 24.dp, end = 24.dp, top = 12.dp))
                    TextButton(onClick = onLogout, colors = plainTextButton(), modifier = Modifier.padding(horizontal = 12.dp)) { Text("Log out") }
                }
            }
        },
    ) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text(state.chats.firstOrNull { it.id == state.chatId }?.title ?: "New chat", maxLines = 1, overflow = TextOverflow.Ellipsis) },
                    navigationIcon = { IconButton(onClick = { scope.launch { drawer.open() } }) { Icon(Icons.Default.Menu, "Chats") } },
                    actions = { IconButton(onClick = viewModel::newChat) { Icon(Icons.Default.Add, "New chat") } },
                )
            },
            bottomBar = {
                Column(Modifier.background(MaterialTheme.colorScheme.background).padding(horizontal = 12.dp).padding(bottom = 8.dp)) {
                    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Corpus.entries.forEach { corpus ->
                            FilterChip(selected = state.corpus == corpus, onClick = { viewModel.setCorpus(corpus) }, enabled = !state.isStreaming, label = { Text(corpus.label) })
                        }
                        if (state.corpus != Corpus.BOTH) {
                            val noun = state.corpus.label.lowercase()
                            FilterChip(
                                selected = state.selectedSources.isNotEmpty(),
                                onClick = { pickingSources = true },
                                enabled = !state.isStreaming,
                                label = { Text(if (state.selectedSources.isEmpty()) "All $noun" else "${state.selectedSources.size} of ${state.pickableSources.size} $noun") },
                            )
                        }
                    }
                    Row(verticalAlignment = Alignment.Bottom) {
                        OutlinedTextField(value = draft, onValueChange = { draft = it }, placeholder = { Text("Ask the library a question…") }, maxLines = 5, modifier = Modifier.weight(1f))
                        IconButton(
                            onClick = send,
                            enabled = canSend,
                            modifier = Modifier.padding(start = 4.dp, bottom = 4.dp).background(MaterialTheme.colorScheme.primary.copy(alpha = if (canSend) 1f else 0.35f), CircleShape),
                        ) { Icon(Icons.AutoMirrored.Filled.Send, "Send", tint = MaterialTheme.colorScheme.onPrimary) }
                    }
                }
            },
            // The screen sits inside the app's own frame, which has already made room for the system bars and keyboard.
            contentWindowInsets = WindowInsets(0, 0, 0, 0),
        ) { padding ->
            Box(Modifier.padding(padding).fillMaxSize()) {
                when {
                    state.isLoadingChat -> Text("Loading chat…", color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.align(Alignment.Center))
                    state.messages.isEmpty() -> EmptyState(onPick = viewModel::send)
                    else -> LazyColumn(state = listState, contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                        items(state.messages, key = { it.id }) { message ->
                            if (message.fromUser) UserBubble(message.text) else AnswerView(message, onCitation = { viewModel.openCitation(message, it) })
                        }
                    }
                }
            }
        }
    }

    if (pickingSources) SourcePicker(state, onToggle = viewModel::toggleSource, onClear = viewModel::clearSources, onClose = { pickingSources = false })

    state.openCitation?.let { open ->
        ModalBottomSheet(onDismissRequest = viewModel::closeCitation) { CitationSheet(open) }
    }

    deleting?.let { chat ->
        AlertDialog(
            onDismissRequest = { deleting = null },
            title = { Text("Delete this chat?") },
            text = { Text("“${chat.title ?: "Untitled chat"}” and its answers will be removed. This cannot be undone.") },
            confirmButton = { TextButton(onClick = { viewModel.deleteChat(chat.id); deleting = null }, colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.error)) { Text("Delete") } },
            dismissButton = { TextButton(onClick = { deleting = null }, colors = plainTextButton()) { Text("Cancel") } },
        )
    }
}

@Composable
private fun EmptyState(onPick: (String) -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        Text("Ask your library something", style = MaterialTheme.typography.titleMedium)
        Text("Answers come from your books and papers, with page-accurate references.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(top = 4.dp, bottom = 20.dp))
        SUGGESTIONS.forEach { suggestion ->
            OutlinedButton(onClick = { onPick(suggestion) }, shape = RoundedCornerShape(12.dp), colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.onSurface), modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                Text(suggestion, modifier = Modifier.fillMaxWidth(), style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

@Composable
private fun UserBubble(text: String) {
    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.CenterEnd) {
        Text(
            text,
            color = MaterialTheme.colorScheme.onPrimary,
            modifier = Modifier.widthIn(max = 300.dp).background(MaterialTheme.colorScheme.primary, RoundedCornerShape(18.dp, 18.dp, 4.dp, 18.dp)).padding(horizontal = 14.dp, vertical = 10.dp),
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun AnswerView(message: UiMessage, onCitation: (Int) -> Unit) {
    val answer = remember(message.text) { renderAnswer(message.text) }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        when {
            answer.text.isNotEmpty() -> SelectionContainer { MarkdownText(answer.text) }
            message.error == null -> Text("Searching the library…", color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        message.error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium) }
        if (answer.references.isNotEmpty()) {
            Text("REFERENCES", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                answer.references.forEachIndexed { index, reference ->
                    Row(
                        Modifier.heightIn(min = 32.dp).widthIn(max = 280.dp).background(MaterialTheme.colorScheme.primaryContainer, CircleShape).clickable { onCitation(index + 1) }.padding(horizontal = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("${index + 1}", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onPrimaryContainer)
                        // The author-year part of an APA reference is enough to recognise it in a chip.
                        Text("  " + reference.substringBefore(").").let { if (it.length < reference.length) "$it)" else it }, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onPrimaryContainer, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
        }
    }
}

@Composable
private fun CitationSheet(open: OpenCitation) {
    val uriHandler = LocalUriHandler.current
    Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 28.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("Reference ${open.number}", style = MaterialTheme.typography.titleMedium)
        SelectionContainer { Text(open.citation.apaText, style = MaterialTheme.typography.bodyMedium) }
        open.citation.locator?.let { Text("Location: $it", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }

        open.item?.let { item ->
            HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant, modifier = Modifier.padding(vertical = 4.dp))
            Text(item.title, style = MaterialTheme.typography.titleSmall)
            val muted = MaterialTheme.colorScheme.onSurfaceVariant
            when (item) {
                is Book -> {
                    item.authors?.let { Text(it + if (item.isEditor) " (Ed.)" else "", style = MaterialTheme.typography.bodySmall, color = muted) }
                    listOfNotNull(item.publisher, item.year?.toString()).takeIf { it.isNotEmpty() }?.let { Text(it.joinToString(", "), style = MaterialTheme.typography.bodySmall, color = muted) }
                    item.edition?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = muted) }
                }
                is Paper -> {
                    item.authors?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = muted) }
                    listOfNotNull(item.venue, item.year?.toString()).takeIf { it.isNotEmpty() }?.let { Text(it.joinToString(", "), style = MaterialTheme.typography.bodySmall, color = muted) }
                    item.doi?.let { doi ->
                        Text("doi.org/$doi", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary, modifier = Modifier.clickable { runCatching { uriHandler.openUri("https://doi.org/$doi") } })
                    }
                    item.abstract?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = muted, modifier = Modifier.padding(top = 4.dp)) }
                }
            }
            if (!item.bibliographyVerified) {
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(top = 4.dp)) {
                    Icon(Icons.Default.Warning, null, tint = MaterialTheme.colorScheme.error, modifier = Modifier.padding(end = 6.dp))
                    Text("Bibliographic data not yet verified against the source", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SourcePicker(state: ChatUiState, onToggle: (String) -> Unit, onClear: () -> Unit, onClose: () -> Unit) {
    var filter by rememberSaveable { mutableStateOf("") }
    val noun = state.corpus.label.lowercase()
    val shown = remember(state.pickableSources, filter) {
        val needle = filter.trim()
        if (needle.isEmpty()) state.pickableSources else state.pickableSources.filter { it.title.contains(needle, ignoreCase = true) || it.authors.orEmpty().contains(needle, ignoreCase = true) }
    }
    ModalBottomSheet(onDismissRequest = onClose, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Limit the search to", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                if (state.selectedSources.isNotEmpty()) TextButton(onClick = onClear, colors = plainTextButton()) { Text("All $noun") }
            }
            OutlinedTextField(value = filter, onValueChange = { filter = it }, placeholder = { Text("Find by title or author") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            LazyColumn(Modifier.fillMaxWidth().heightIn(max = 420.dp)) {
                items(shown, key = LibraryItem::sourceKey) { item ->
                    Row(Modifier.fillMaxWidth().clickable { onToggle(item.sourceKey) }.padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = item.sourceKey in state.selectedSources, onCheckedChange = { onToggle(item.sourceKey) })
                        Column(Modifier.weight(1f)) {
                            Text(item.title, style = MaterialTheme.typography.bodyMedium, maxLines = 2, overflow = TextOverflow.Ellipsis)
                            listOfNotNull(item.authors, item.year?.toString()).takeIf { it.isNotEmpty() }?.let {
                                Text(it.joinToString(" · "), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            }
                        }
                    }
                }
                if (shown.isEmpty()) item { Text(if (state.pickableSources.isEmpty()) "No $noun in the library yet." else "Nothing matches.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(12.dp)) }
            }
        }
    }
}
