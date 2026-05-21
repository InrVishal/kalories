pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
    // versionCatalogs are automatically resolved by Gradle if gradle/libs.versions.toml exists
}

rootProject.name = "Kalories"
include(":app")
