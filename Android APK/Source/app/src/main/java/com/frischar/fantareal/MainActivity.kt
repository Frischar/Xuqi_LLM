package com.frischar.fantareal

import android.annotation.SuppressLint
import android.net.Uri
import android.os.Bundle
import android.util.Base64
import android.view.Display
import android.webkit.CookieManager
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.isVisible
import com.frischar.fantareal.databinding.ActivityMainBinding

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private var fileChooserCallback: ValueCallback<Array<Uri>>? = null
    private var pendingSaveRequest: PendingSaveRequest? = null
    private var pendingImagePickRequestId: String? = null

    private val filePicker =
        registerForActivityResult(ActivityResultContracts.GetMultipleContents()) { uris ->
            fileChooserCallback?.onReceiveValue(uris.toTypedArray())
            fileChooserCallback = null
        }

    private val saveFilePicker =
        registerForActivityResult(ActivityResultContracts.CreateDocument("*/*")) { uri ->
            handleSaveResult(uri)
        }

    private val imagePicker =
        registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
            handleImagePickResult(uri)
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        preferHighRefreshRate()

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (binding.webView.canGoBack()) {
                    binding.webView.goBack()
                } else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })

        configureWebView()
        loadLocalApp()
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configureWebView() {
        with(binding.webView.settings) {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = true
            allowContentAccess = true
            cacheMode = WebSettings.LOAD_DEFAULT
            loadsImagesAutomatically = true
            loadWithOverviewMode = true
            useWideViewPort = true
            setSupportZoom(false)
            builtInZoomControls = false
            displayZoomControls = false
            offscreenPreRaster = true
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
            mediaPlaybackRequiresUserGesture = false
        }

        binding.webView.addJavascriptInterface(
            MobileBridge(
                binding.webView,
                { fileName, mimeType, content, requestId ->
                    requestSaveTextFile(fileName, mimeType, content, requestId)
                },
                { fileName, mimeType, base64Content, requestId ->
                    requestSaveBinaryFile(fileName, mimeType, base64Content, requestId)
                },
                { requestId ->
                    requestPickImage(requestId)
                }
            ),
            "XuqiNative"
        )

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(binding.webView, true)
        binding.webView.overScrollMode = WebView.OVER_SCROLL_NEVER

        binding.webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                binding.progressBar.isVisible = false
            }
        }

        binding.webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?
            ): Boolean {
                fileChooserCallback?.onReceiveValue(null)
                fileChooserCallback = filePathCallback
                filePicker.launch("*/*")
                return true
            }
        }
    }

    private fun loadLocalApp() {
        binding.progressBar.isVisible = true
        binding.webView.loadUrl(LOCAL_APP_URL)
    }

    private fun preferHighRefreshRate() {
        val targetRate = runCatching {
            @Suppress("DEPRECATION")
            val currentDisplay = windowManager.defaultDisplay
            val maxModeRate = currentDisplay?.supportedModes?.maxOfOrNull(Display.Mode::getRefreshRate)
            maxModeRate ?: currentDisplay?.refreshRate ?: 120f
        }.getOrDefault(120f)

        val params = window.attributes
        if (targetRate > 0f) {
            params.preferredRefreshRate = targetRate
            window.attributes = params
        }
    }

    private fun requestSaveTextFile(fileName: String, mimeType: String, content: String, requestId: String) {
        requestSaveFile(fileName, mimeType, content.toByteArray(Charsets.UTF_8), requestId)
    }

    private fun requestSaveBinaryFile(fileName: String, mimeType: String, base64Content: String, requestId: String) {
        requestSaveFile(fileName, mimeType, Base64.decode(base64Content, Base64.DEFAULT), requestId)
    }

    private fun requestSaveFile(fileName: String, mimeType: String, bytes: ByteArray, requestId: String) {
        runOnUiThread {
            pendingSaveRequest = PendingSaveRequest(fileName, mimeType, bytes, requestId)
            saveFilePicker.launch(fileName)
        }
    }

    private fun requestPickImage(requestId: String) {
        runOnUiThread {
            pendingImagePickRequestId = requestId
            imagePicker.launch("image/*")
        }
    }

    private fun handleSaveResult(uri: Uri?) {
        val pending = pendingSaveRequest ?: return
        pendingSaveRequest = null

        if (uri == null) {
            dispatchSaveResult(pending.requestId, ok = false, error = "已取消导出")
            return
        }

        runCatching {
            contentResolver.openOutputStream(uri)?.use { stream ->
                stream.write(pending.bytes)
                stream.flush()
            } ?: error("无法写入目标文件")
        }.onSuccess {
            dispatchSaveResult(pending.requestId, ok = true, uri = uri.toString())
        }.onFailure { throwable ->
            dispatchSaveResult(
                pending.requestId,
                ok = false,
                error = throwable.message ?: "文件导出失败"
            )
        }
    }

    private fun handleImagePickResult(uri: Uri?) {
        val requestId = pendingImagePickRequestId ?: return
        pendingImagePickRequestId = null

        if (uri == null) {
            dispatchImagePickResult(requestId, ok = false, error = "已取消选择图片")
            return
        }

        runCatching {
            val mimeType = contentResolver.getType(uri)?.takeIf { it.isNotBlank() } ?: "image/*"
            val bytes = contentResolver.openInputStream(uri)?.use { stream ->
                stream.readBytes()
            } ?: error("无法读取图片内容")
            val encoded = Base64.encodeToString(bytes, Base64.NO_WRAP)
            "data:$mimeType;base64,$encoded"
        }.onSuccess { dataUrl ->
            dispatchImagePickResult(requestId, ok = true, dataUrl = dataUrl)
        }.onFailure { throwable ->
            dispatchImagePickResult(
                requestId,
                ok = false,
                error = throwable.message ?: "图片读取失败"
            )
        }
    }

    private fun dispatchSaveResult(requestId: String, ok: Boolean, uri: String? = null, error: String? = null) {
        val payload = buildString {
            append("{")
            append("\"requestId\":")
            append(org.json.JSONObject.quote(requestId))
            append(",\"ok\":")
            append(ok)
            if (uri != null) {
                append(",\"uri\":")
                append(org.json.JSONObject.quote(uri))
            }
            if (error != null) {
                append(",\"error\":")
                append(org.json.JSONObject.quote(error))
            }
            append("}")
        }
        val escaped = org.json.JSONObject.quote(payload)
        binding.webView.post {
            binding.webView.evaluateJavascript(
                "window.XuqiMobileApp && window.XuqiMobileApp.onNativeSaveResult($escaped);",
                null
            )
        }
    }

    private fun dispatchImagePickResult(requestId: String, ok: Boolean, dataUrl: String? = null, error: String? = null) {
        val payload = buildString {
            append("{")
            append("\"requestId\":")
            append(org.json.JSONObject.quote(requestId))
            append(",\"ok\":")
            append(ok)
            if (dataUrl != null) {
                append(",\"dataUrl\":")
                append(org.json.JSONObject.quote(dataUrl))
            }
            if (error != null) {
                append(",\"error\":")
                append(org.json.JSONObject.quote(error))
            }
            append("}")
        }
        val escaped = org.json.JSONObject.quote(payload)
        binding.webView.post {
            binding.webView.evaluateJavascript(
                "window.XuqiMobileApp && window.XuqiMobileApp.onNativeImagePickResult($escaped);",
                null
            )
        }
    }

    private data class PendingSaveRequest(
        val fileName: String,
        val mimeType: String,
        val bytes: ByteArray,
        val requestId: String
    )

    companion object {
        private const val LOCAL_APP_URL = "file:///android_asset/mobile/index.html"
    }
}
