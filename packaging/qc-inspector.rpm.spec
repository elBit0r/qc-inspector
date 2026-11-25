# Preserve the PyInstaller bundle byte for byte and declare its system
# dependencies explicitly. Private bundled libraries are not system providers.
%global __os_install_post %{nil}
%global debug_package %{nil}

Name: qc-inspector
Version: %{app_version}
Release: 1
Summary: QC Inspector desktop application
License: AGPL-3.0-only
ExclusiveArch: x86_64
AutoReqProv: no
Requires: glibc%{?_isa} >= %{glibc_min}
Requires: libstdc++%{?_isa}
Requires: cups-client
Requires: xdg-utils
Requires: gstreamer1%{?_isa}
Requires: gstreamer1-plugins-base%{?_isa}
Requires: gstreamer1-plugins-good%{?_isa}
Requires: libEGL.so.1()(64bit)
Requires: libGL.so.1()(64bit)
Requires: libdrm.so.2()(64bit)
Requires: libxcb.so.1()(64bit)
Requires: libxcb-cursor.so.0()(64bit)
Requires: libwayland-client.so.0()(64bit)
Requires: libwayland-cursor.so.0()(64bit)
Requires: libwayland-egl.so.1()(64bit)
Requires(pre): coreutils
Requires(post): coreutils, shadow-utils, /usr/bin/getent

%description
PyQt-based tool for setup programming and dimensional inspection.

%install
mkdir -p "%{buildroot}"
cp -a "$QC_INSPECTOR_PACKAGE_ROOT/etc" "$QC_INSPECTOR_PACKAGE_ROOT/opt" \
  "$QC_INSPECTOR_PACKAGE_ROOT/usr" "%{buildroot}/"

%pre -p /bin/bash -f %{_topdir}/preinst

%post -p /bin/bash -f %{_topdir}/postinst

%files
/opt/qc-inspector
%dir /etc/qc-inspector
%config(noreplace) /etc/qc-inspector/qc_inspector.conf
/usr/bin/qc-inspector
/usr/share/applications/qc-inspector.desktop
/usr/share/icons/hicolor/512x512/apps/qc-inspector.png
/usr/share/doc/qc-inspector
