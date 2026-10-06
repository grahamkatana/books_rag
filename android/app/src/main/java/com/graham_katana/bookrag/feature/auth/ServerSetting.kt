package com.graham_katana.bookrag.feature.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.graham_katana.bookrag.core.network.ServerSettings

/**
 * A quiet gear for the corner of the login screen. It opens the dialog that sets which server the
 * app talks to. The address itself is never shown on the screen, only inside the dialog, and only
 * when it has been changed from the standard one.
 */
@Composable
fun ServerSetting(server: ServerSettings, modifier: Modifier = Modifier) {
    val url by server.url.collectAsStateWithLifecycle()
    var editing by rememberSaveable { mutableStateOf(false) }
    val plain = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.onSurfaceVariant)

    IconButton(onClick = { editing = true }, modifier = modifier) {
        Icon(Icons.Default.Settings, "Configure server", tint = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f))
    }

    if (editing) {
        var draft by rememberSaveable { mutableStateOf(if (server.isCustom) url else "") }
        var invalid by rememberSaveable { mutableStateOf(false) }
        AlertDialog(
            onDismissRequest = { editing = false },
            title = { Text("Server address") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text("Only change this if you run your own Book RAG server. Leave it empty to use the standard one.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    OutlinedTextField(
                        value = draft,
                        onValueChange = { draft = it; invalid = false },
                        label = { Text("Address") },
                        placeholder = { Text("https://rag.example.org") },
                        singleLine = true,
                        isError = invalid,
                        supportingText = if (invalid) { { Text("Enter a full https address, such as https://rag.example.org") } } else null,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, autoCorrectEnabled = false),
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            },
            confirmButton = {
                TextButton(colors = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.onSurface), onClick = {
                    if (draft.isBlank()) { server.reset(); editing = false } else if (server.set(draft)) editing = false else invalid = true
                }) { Text("Save") }
            },
            dismissButton = { TextButton(onClick = { editing = false }, colors = plain) { Text("Cancel") } },
        )
    }
}
