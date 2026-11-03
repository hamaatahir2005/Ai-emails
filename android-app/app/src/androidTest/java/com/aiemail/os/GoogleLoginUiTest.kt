package com.aiemail.os

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.assertIsNotEnabled
import androidx.compose.ui.test.performClick
import com.aiemail.os.ui.LoginForm
import com.aiemail.os.ui.OsTheme
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test

class GoogleLoginUiTest {
    @get:Rule val compose = createComposeRule()

    @Test fun configured_google_button_starts_sign_in() {
        var clicked = 0
        compose.setContent {
            OsTheme { LoginForm(googleConfigured = true, onPasswordSignIn = { _, _ -> }, onGoogleSignIn = { clicked++ }) }
        }
        compose.onNodeWithTag("google_sign_in").assertIsEnabled().performClick()
        assertEquals(1, clicked)
    }

    @Test fun missing_configuration_explains_disabled_button() {
        compose.setContent {
            OsTheme { LoginForm(googleConfigured = false, onPasswordSignIn = { _, _ -> }, onGoogleSignIn = {}) }
        }
        compose.onNodeWithTag("google_sign_in").assertIsNotEnabled()
        compose.onNodeWithText("Google sign-in requires configuration by the administrator.").assertIsDisplayed()
    }

    @Test fun busy_login_prevents_duplicate_google_requests() {
        compose.setContent {
            OsTheme { LoginForm(googleConfigured = true, busy = true, onPasswordSignIn = { _, _ -> }, onGoogleSignIn = {}) }
        }
        compose.onNodeWithTag("google_sign_in").assertIsNotEnabled()
    }
}
