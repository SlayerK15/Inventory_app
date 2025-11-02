package com.example.inventory

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    InventoryScreen()
                }
            }
        }
    }
}

data class InventoryItem(
    val id: Int,
    val sku: String,
    val name: String,
    val description: String?,
    val quantity: Int,
    val location: String?,
    val reorder_point: Int
)

data class DashboardSummary(
    val user: UserProfile,
    val inventory: List<InventoryItem>,
    val low_stock: List<InventoryItem>
)

data class UserProfile(
    val email: String,
    val full_name: String,
    val role: String,
    val tenant_id: String
)

data class LoginRequest(val email: String, val password: String)

data class LoginResponse(val access_token: String, val token_type: String)

interface GatewayApi {
    @POST("/auth/login")
    suspend fun login(@Body request: LoginRequest): LoginResponse

    @GET("/dashboard")
    suspend fun dashboard(@Header("Authorization") token: String): DashboardSummary
}

private fun provideApi(): GatewayApi = Retrofit.Builder()
    .baseUrl("http://10.0.2.2:8080")
    .addConverterFactory(MoshiConverterFactory.create())
    .build()
    .create(GatewayApi::class.java)

@Composable
fun InventoryScreen(api: GatewayApi = provideApi()) {
    val scope = rememberCoroutineScope()
    var email by remember { mutableStateOf("staff@example.com") }
    var password by remember { mutableStateOf("password123") }
    var token by remember { mutableStateOf<String?>(null) }
    val items = remember { mutableStateListOf<InventoryItem>() }
    val alerts = remember { mutableStateListOf<InventoryItem>() }
    var status by remember { mutableStateOf<String?>(null) }

    fun loadDashboard(currentToken: String) {
        scope.launch {
            status = "Loading inventory…"
            try {
                val dashboard = withContext(Dispatchers.IO) {
                    api.dashboard("Bearer $currentToken")
                }
                items.clear()
                items.addAll(dashboard.inventory)
                alerts.clear()
                alerts.addAll(dashboard.low_stock)
                status = "Loaded ${dashboard.inventory.size} items"
            } catch (ex: Exception) {
                status = ex.localizedMessage
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Text(text = "Inventory Gateway", style = MaterialTheme.typography.headlineSmall)

        if (token == null) {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Sign in to manage inventory", style = MaterialTheme.typography.bodyMedium)
                OutlinedTextField(
                    value = email,
                    onValueChange = { email = it },
                    label = { Text("Email") },
                    modifier = Modifier.fillMaxWidth()
                )
                OutlinedTextField(
                    value = password,
                    onValueChange = { password = it },
                    label = { Text("Password") },
                    visualTransformation = PasswordVisualTransformation(),
                    modifier = Modifier.fillMaxWidth()
                )
                Button(
                    onClick = {
                        scope.launch {
                            status = "Signing in…"
                            try {
                                val response = withContext(Dispatchers.IO) {
                                    api.login(LoginRequest(email, password))
                                }
                                token = response.access_token
                                status = "Signed in"
                                loadDashboard(response.access_token)
                            } catch (ex: Exception) {
                                status = ex.localizedMessage
                            }
                        }
                    },
                    modifier = Modifier.align(Alignment.End)
                ) {
                    Text("Sign in")
                }
            }
        } else {
            Button(onClick = { token = null; items.clear(); alerts.clear() }) {
                Text("Sign out")
            }
            Button(onClick = { loadDashboard(token!!) }) {
                Text("Refresh inventory")
            }
            if (status != null) {
                Text(text = status!!, style = MaterialTheme.typography.bodySmall)
            }
            LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                items(items) { item ->
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text(text = item.name, style = MaterialTheme.typography.titleMedium)
                            Text(text = "SKU: ${item.sku}")
                            Text(text = "Quantity: ${item.quantity}")
                            Text(text = "Reorder point: ${item.reorder_point}")
                        }
                    }
                }
            }
            if (alerts.isNotEmpty()) {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("Low stock alerts", style = MaterialTheme.typography.titleMedium)
                    alerts.forEach { alert ->
                        Text("${alert.name} (${alert.sku}) is at ${alert.quantity} units")
                    }
                }
            }
        }
    }
}
