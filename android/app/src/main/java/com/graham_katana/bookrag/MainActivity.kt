package com.graham_katana.bookrag

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.graham_katana.bookrag.core.ui.BookRagTheme
import com.graham_katana.bookrag.feature.auth.LoginScreen
import com.graham_katana.bookrag.feature.auth.LoginViewModel
import com.graham_katana.bookrag.feature.chat.ChatScreen
import com.graham_katana.bookrag.feature.chat.ChatViewModel
import com.graham_katana.bookrag.feature.verify.VerifyScreen
import com.graham_katana.bookrag.feature.verify.VerifyViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Edge to edge, with bar icons that follow the phone's light or dark setting, as the app's colours do.
        enableEdgeToEdge()
        val container = (application as BookRagApp).container
        setContent {
            BookRagTheme {
                Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    val account by container.session.account.collectAsStateWithLifecycle()
                    val current = account
                    if (current == null) {
                        LoginScreen(viewModel(factory = viewModelFactory { initializer { LoginViewModel(container.auth) } }), container.server)
                    } else {
                        // Keyed by who is logged in, so a second person never sees the first one's chats or drafts.
                        Home(container, email = current.email)
                    }
                }
            }
        }
    }
}

@Composable
private fun Home(container: AppContainer, email: String) {
    var tab by rememberSaveable(email) { mutableIntStateOf(0) }
    val chat: ChatViewModel = viewModel(key = "chat-$email", factory = viewModelFactory { initializer { ChatViewModel(container.chat, container.library) } })
    val verify: VerifyViewModel = viewModel(key = "verify-$email", factory = viewModelFactory { initializer { VerifyViewModel(container.verify) } })

    Scaffold(
        bottomBar = {
            // Material's own bar is 80dp tall, which pushes the tabs well up the screen. This one is 52dp
            // and sits directly above the system navigation area.
            Surface(color = MaterialTheme.colorScheme.surface) {
                Column(Modifier.navigationBarsPadding()) {
                    HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                    Row(Modifier.fillMaxWidth().height(52.dp)) {
                        Tab("Ask", Icons.Default.Search, selected = tab == 0, onClick = { tab = 0 })
                        Tab("Verify", Icons.Default.CheckCircle, selected = tab == 1, onClick = { tab = 1 })
                    }
                }
            }
        },
    ) { padding ->
        // This frame makes room for the system bars and the tab bar; the keyboard then only pushes up what is left.
        Box(Modifier.padding(bottom = padding.calculateBottomPadding()).consumeWindowInsets(PaddingValues(bottom = padding.calculateBottomPadding())).imePadding().fillMaxSize()) {
            if (tab == 0) ChatScreen(chat, email = email, onLogout = container.session::end) else VerifyScreen(verify)
        }
    }
}

/** One tab: icon beside its label, blue when it is the open one. */
@Composable
private fun RowScope.Tab(label: String, icon: ImageVector, selected: Boolean, onClick: () -> Unit) {
    val color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
    Row(
        Modifier.weight(1f).fillMaxHeight().clickable(role = Role.Tab, onClick = onClick),
        horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, null, tint = color, modifier = Modifier.size(20.dp))
        Text(label, color = color, style = MaterialTheme.typography.labelLarge)
    }
}
