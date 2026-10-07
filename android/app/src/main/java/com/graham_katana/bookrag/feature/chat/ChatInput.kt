package com.graham_katana.bookrag.feature.chat

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp

/**
 * The message box, laid out like a messaging app: a rounded field that grows with the text, and one round button
 * beside it that is a microphone while the box is empty and Send once there is text.
 */
@Composable
fun ChatInput(
    draft: String,
    onDraft: (String) -> Unit,
    placeholder: String,
    listening: Boolean,
    canSend: Boolean,
    busy: Boolean,
    onSend: () -> Unit,
    onMic: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val hasText = draft.isNotBlank()
    val colors = MaterialTheme.colorScheme
    Row(modifier, verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Surface(
            modifier = Modifier.weight(1f),
            shape = RoundedCornerShape(24.dp),
            color = colors.surface,
            border = BorderStroke(1.dp, colors.outline.copy(alpha = 0.5f)),
        ) {
            BasicTextField(
                value = draft,
                onValueChange = onDraft,
                maxLines = 6,
                textStyle = MaterialTheme.typography.bodyLarge.copy(color = colors.onSurface),
                cursorBrush = SolidColor(colors.primary),
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 11.dp),
                decorationBox = { inner ->
                    Box(contentAlignment = Alignment.CenterStart) {
                        if (draft.isEmpty()) Text(placeholder, style = MaterialTheme.typography.bodyLarge, color = colors.onSurfaceVariant, maxLines = 1)
                        inner()
                    }
                },
            )
        }
        val enabled = if (hasText) canSend else !busy || listening
        Box(
            Modifier
                .size(46.dp)
                .background(if (listening) colors.error else colors.primary.copy(alpha = if (enabled) 1f else 0.35f), CircleShape)
                .clickable(enabled = enabled, role = Role.Button, onClick = if (hasText) onSend else onMic),
            contentAlignment = Alignment.Center,
        ) {
            val tint = if (listening) colors.onError else colors.onPrimary
            when {
                hasText -> Icon(Icons.AutoMirrored.Filled.Send, "Send", Modifier.size(20.dp), tint = tint)
                listening -> Icon(VoiceIcons.Stop, "Stop dictating", Modifier.size(20.dp), tint = tint)
                else -> Icon(VoiceIcons.Mic, "Speak your question", Modifier.size(22.dp), tint = tint)
            }
        }
    }
}

/** A compact single-line field for forms: a small label above, a 44 dp rounded box below. */
@Composable
fun CompactField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    visualTransformation: VisualTransformation = VisualTransformation.None,
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default,
    keyboardActions: KeyboardActions = KeyboardActions.Default,
) {
    val colors = MaterialTheme.colorScheme
    Column(modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = colors.onSurfaceVariant)
        Surface(shape = RoundedCornerShape(10.dp), color = colors.surface, border = BorderStroke(1.dp, colors.outline.copy(alpha = 0.6f))) {
            BasicTextField(
                value = value,
                onValueChange = onValueChange,
                singleLine = true,
                textStyle = MaterialTheme.typography.bodyLarge.copy(color = colors.onSurface),
                cursorBrush = SolidColor(colors.primary),
                visualTransformation = visualTransformation,
                keyboardOptions = keyboardOptions,
                keyboardActions = keyboardActions,
                modifier = Modifier.fillMaxWidth().heightIn(min = 44.dp).padding(horizontal = 14.dp, vertical = 11.dp),
            )
        }
    }
}
