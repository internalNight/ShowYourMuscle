package com.muscleatlas.prototype;

import static org.junit.Assert.*;

import android.content.Context;
import android.content.res.AssetManager;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import org.junit.Test;
import org.junit.runner.RunWith;

/**
 * Device smoke test: the installed package must be this app, and the web build must actually be
 * packaged inside it. The asset assertion catches an APK that was compiled without running
 * `npx cap sync`, which would otherwise only show up as a blank WebView on a device.
 */
@RunWith(AndroidJUnit4.class)
public class ExampleInstrumentedTest {

    @Test
    public void useAppContext() throws Exception {
        Context appContext = InstrumentationRegistry.getInstrumentation().getTargetContext();

        assertEquals("com.muscleatlas.prototype", appContext.getPackageName());
    }

    @Test
    public void packagedWebBuildIsPresent() throws Exception {
        AssetManager assets = InstrumentationRegistry.getInstrumentation()
            .getTargetContext().getAssets();

        StringBuilder html = new StringBuilder();
        try (InputStream stream = assets.open("public/index.html")) {
            byte[] buffer = new byte[8192];
            int read;
            while ((read = stream.read(buffer)) > 0) {
                html.append(new String(buffer, 0, read, StandardCharsets.UTF_8));
            }
        }
        // The inline bundle embeds the service-worker cache token; the prefix only is asserted so a
        // cache version bump does not break the test.
        assertTrue("packaged index.html is empty", html.length() > 100000);
        assertTrue("packaged index.html is missing the offline cache token",
            html.indexOf("muscle-atlas-v") >= 0);
    }
}
