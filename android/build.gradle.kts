// Nothing builds at the root: the modules below declare their own plugins. This file only keeps the
// version catalog and the plugins available to both modules with one number each.
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.jvm) apply false
    alias(libs.plugins.kotlin.serialization) apply false
}
