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
        // Nordic Semiconductor repos
        maven { url = uri("https://maven.nordicsemi.com/public") }
    }
}

rootProject.name = "PlanetaryHub"
include(":app")
