package com.frischar.fantareal

import android.webkit.JavascriptInterface
import android.webkit.WebView
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStream
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL

class MobileBridge(
    private val webView: WebView,
    private val saveTextFileRequest: (String, String, String, String) -> Unit,
    private val saveBinaryFileRequest: (String, String, String, String) -> Unit,
    private val pickImageRequest: (String) -> Unit
) {

    @JavascriptInterface
    fun postChat(payloadJson: String): String {
        return runChatRequest(payloadJson).toString()
    }

    @JavascriptInterface
    fun postChatAsync(payloadJson: String, requestId: String) {
        Thread {
            val result = runChatRequest(payloadJson).put("requestId", requestId)
            val escaped = JSONObject.quote(result.toString())
            webView.post {
                webView.evaluateJavascript(
                    "window.XuqiMobileApp && window.XuqiMobileApp.onNativeChatResult($escaped);",
                    null
                )
            }
        }.start()
    }

    @JavascriptInterface
    fun saveTextFileAsync(fileName: String, mimeType: String, content: String, requestId: String) {
        saveTextFileRequest(fileName, mimeType, content, requestId)
    }

    @JavascriptInterface
    fun saveBinaryFileAsync(fileName: String, mimeType: String, base64Content: String, requestId: String) {
        saveBinaryFileRequest(fileName, mimeType, base64Content, requestId)
    }

    @JavascriptInterface
    fun pickImageAsync(requestId: String) {
        pickImageRequest(requestId)
    }

    private fun runChatRequest(payloadJson: String): JSONObject {
        return try {
            val payload = JSONObject(payloadJson)
            val apiBaseUrl = payload.optString("apiBaseUrl").trim()
            val apiKey = payload.optString("apiKey").trim()
            val model = payload.optString("model").trim()
            val timeoutSec = payload.optInt("timeoutSec", 90).coerceIn(15, 300)
            val temperature = payload.optDouble("temperature", 0.85)
            val maxTokens = payload.optInt("maxTokens", 0).coerceAtLeast(0)
            val messages = payload.optJSONArray("messages") ?: JSONArray()

            if (apiBaseUrl.isBlank() || model.isBlank()) {
                return JSONObject()
                    .put("ok", false)
                    .put("error", "请先在配置页填写 API URL 和模型名。")
            }

            val endpoint = normalizeEndpoint(apiBaseUrl)
            val requestBody = JSONObject()
                .put("model", model)
                .put("messages", messages)
                .put("temperature", temperature)
                .put("stream", false)
            if (maxTokens > 0) {
                requestBody.put("max_tokens", maxTokens)
            }

            val responseText = postJsonWithRetry(
                url = endpoint,
                body = requestBody.toString(),
                apiKey = apiKey,
                timeoutSec = timeoutSec
            )
            val responseJson = JSONObject(responseText)
            val content = extractAssistantText(responseJson)

            JSONObject()
                .put("ok", true)
                .put("content", content)
        } catch (exc: Exception) {
            JSONObject()
                .put("ok", false)
                .put("error", exc.message ?: "请求失败")
        }
    }

    private fun normalizeEndpoint(baseUrl: String): String {
        val trimmed = baseUrl.trim().trimEnd('/')
        return if (trimmed.endsWith("/chat/completions")) trimmed else "$trimmed/chat/completions"
    }

    private fun postJsonWithRetry(
        url: String,
        body: String,
        apiKey: String,
        timeoutSec: Int
    ): String {
        var lastError: IllegalStateException? = null
        for (attemptIndex in 0 until MAX_ATTEMPTS) {
            val result = postJsonOnce(url, body, apiKey, timeoutSec)
            if (result.success) return result.body

            val code = result.code
            lastError = IllegalStateException(buildErrorMessage(code, result.body))
            if (!shouldRetryStatus(code) || attemptIndex == MAX_ATTEMPTS - 1) {
                throw lastError
            }

            Thread.sleep(RETRY_BACKOFF_MS * (attemptIndex + 1))
        }

        throw lastError ?: IllegalStateException("模型接口请求失败")
    }

    private fun postJsonOnce(
        url: String,
        body: String,
        apiKey: String,
        timeoutSec: Int
    ): HttpResult {
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = timeoutSec * 1000
            readTimeout = timeoutSec * 1000
            doOutput = true
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Accept", "application/json")
            if (apiKey.isNotBlank()) {
                setRequestProperty("Authorization", "Bearer $apiKey")
            }
        }

        OutputStreamWriter(conn.outputStream, Charsets.UTF_8).use { writer ->
            writer.write(body)
            writer.flush()
        }

        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val responseText = readBody(stream)
        return HttpResult(code in 200..299, code, responseText)
    }

    private fun readBody(stream: InputStream?): String {
        if (stream == null) return ""
        return BufferedReader(InputStreamReader(stream, Charsets.UTF_8)).use { reader ->
            reader.readText()
        }
    }

    private fun shouldRetryStatus(code: Int): Boolean {
        return code == 408 || code == 409 || code == 425 || code == 429 || code == 529 || code in 500..599
    }

    private fun buildErrorMessage(code: Int, responseText: String): String {
        val compact = responseText.replace(Regex("\\s+"), " ").trim()
        return if (compact.isBlank()) {
            "模型接口返回错误 ($code)"
        } else {
            "模型接口返回错误 ($code): $compact"
        }
    }

    private fun extractAssistantText(responseJson: JSONObject): String {
        val choices = responseJson.optJSONArray("choices") ?: JSONArray()
        if (choices.length() > 0) {
            val first = choices.optJSONObject(0)
            val message = first?.optJSONObject("message")
            extractTextValue(message?.opt("content"))?.let { if (it.isNotBlank()) return it }
            extractTextValue(first?.opt("text"))?.let { if (it.isNotBlank()) return it }
        }

        extractTextValue(responseJson.opt("output_text"))?.let { if (it.isNotBlank()) return it }
        extractTextValue(responseJson.opt("reply"))?.let { if (it.isNotBlank()) return it }

        responseJson.optJSONObject("data")?.let { data ->
            extractTextValue(data.opt("output_text"))?.let { if (it.isNotBlank()) return it }
            extractTextValue(data.opt("reply"))?.let { if (it.isNotBlank()) return it }
        }

        throw IllegalStateException("接口返回里没有可用的回复文本。")
    }

    private fun extractTextValue(value: Any?): String? {
        return when (value) {
            null -> null
            is String -> value
            is JSONArray -> {
                val parts = mutableListOf<String>()
                for (index in 0 until value.length()) {
                    val item = value.opt(index)
                    when (item) {
                        is String -> if (item.isNotBlank()) parts += item
                        is JSONObject -> {
                            val text = item.optString("text").trim()
                            if (text.isNotBlank()) {
                                parts += text
                            } else {
                                val innerText = item.optJSONObject("text")?.optString("value")?.trim().orEmpty()
                                if (innerText.isNotBlank()) parts += innerText
                            }
                        }
                    }
                }
                parts.joinToString("")
            }
            else -> value.toString()
        }
    }

    private data class HttpResult(
        val success: Boolean,
        val code: Int,
        val body: String
    )

    companion object {
        private const val MAX_ATTEMPTS = 3
        private const val RETRY_BACKOFF_MS = 700L
    }
}
