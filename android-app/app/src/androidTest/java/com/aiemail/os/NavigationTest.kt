package com.aiemail.os

import androidx.compose.material3.Text
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.assertIsDisplayed
import com.aiemail.os.ui.OsScaffold
import com.aiemail.os.ui.OsTheme
import org.junit.Rule
import org.junit.Test

class NavigationTest {
    @get:Rule val compose = createComposeRule()
    @Test fun all_destinations_are_reachable_and_stop_requires_confirmation() {
        var stopped = false
        compose.setContent { OsTheme { OsScaffold(onStop = { stopped = true }) { Text("destination-$it") } } }
        compose.onNodeWithText("destination-0").assertIsDisplayed()
        listOf("Customers", "Campaigns", "Analytics", "Settings").forEachIndexed { index, label ->
            compose.onNodeWithText(label, useUnmergedTree = true).performClick()
            compose.onNodeWithText("destination-${index + 1}").assertIsDisplayed()
        }
        compose.onNodeWithContentDescription("Emergency stop").performClick()
        org.junit.Assert.assertFalse(stopped)
        compose.onNodeWithText("Confirm").performClick()
        org.junit.Assert.assertTrue(stopped)
    }
}
