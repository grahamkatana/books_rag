package com.graham_katana.bookrag.core.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.width
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp

@Composable
fun MarkdownText(text: String, modifier: Modifier = Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        parseMarkdown(text).forEach { block ->
            when (block) {
                is MdBlock.Heading -> Text(styled(block.spans), style = if (block.level <= 2) MaterialTheme.typography.titleMedium else MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                is MdBlock.Paragraph -> Text(styled(block.spans), style = MaterialTheme.typography.bodyLarge)
                is MdBlock.Bullets -> Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    block.items.forEach { Row { Text("•  ", style = MaterialTheme.typography.bodyLarge); Text(styled(it), style = MaterialTheme.typography.bodyLarge) } }
                }
                is MdBlock.Numbered -> Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    block.items.forEachIndexed { index, item -> Row { Text("${index + 1}.  ", style = MaterialTheme.typography.bodyLarge); Text(styled(item), style = MaterialTheme.typography.bodyLarge) } }
                }
                is MdBlock.Table -> TableView(block)
            }
        }
    }
}

/** A table scrolls sideways instead of squeezing its columns to nothing on a phone. */
@Composable
private fun TableView(table: MdBlock.Table) {
    val columns = maxOf(table.header.size, table.rows.maxOfOrNull { it.size } ?: 0)
    Column(Modifier.horizontalScroll(rememberScrollState()).border(1.dp, MaterialTheme.colorScheme.outline)) {
        @Composable fun row(cells: List<List<Span>>, bold: Boolean) = Row {
            for (c in 0 until columns) {
                Text(
                    styled(cells.getOrElse(c) { emptyList() }),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = if (bold) FontWeight.SemiBold else null,
                    modifier = Modifier.width(112.dp).padding(horizontal = 8.dp, vertical = 6.dp),
                )
            }
        }
        row(table.header, bold = true)
        table.rows.forEach { HorizontalDivider(color = MaterialTheme.colorScheme.outline); row(it, bold = false) }
    }
}

@Composable
private fun styled(spans: List<Span>): AnnotatedString = buildAnnotatedString {
    spans.forEach { span ->
        withStyle(
            SpanStyle(
                fontWeight = if (span.bold) FontWeight.Bold else null,
                fontStyle = if (span.italic) FontStyle.Italic else null,
                fontFamily = if (span.code) FontFamily.Monospace else null,
            )
        ) { append(span.text) }
    }
}
