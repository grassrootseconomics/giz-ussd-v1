# standard imports
import semver

version = (0, 3, 3)

version_object = semver.VersionInfo(
        major=version[0],
        minor=version[1],
        patch=version[2]
        )

version_string = str(version_object)
