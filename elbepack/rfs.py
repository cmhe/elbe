# ELBE - Debian Based Embedded Rootfilesystem Builder
# Copyright (C) 2013  Linutronix GmbH
#
# This file is part of ELBE.
#
# ELBE is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ELBE is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ELBE.  If not, see <http://www.gnu.org/licenses/>.

import apt
import apt_pkg
import os
import stat
import sys
import time

from elbepack.version import elbe_version

from tempfile import mkdtemp

def mkdir_p (newdir, mode=0777):
        """works the way a good mkdir -p would...
                - already exists, silently complete
                - regular file in the way, raise an exception
                - parent directory(ies) does not exist, make them as well
        """
        if os.path.isdir (newdir):
                pass
        elif os.path.isfile (newdir):
                raise OSError ("a file with the same name as the desired " \
                               "dir, '%s', already exists." % newdir)
        else:
                os.makedirs (newdir, mode)
                """ mode is not set correctly """
                os.system ("chmod 777 "+newdir)

def touch_file (file):
        if os.path.exists (file):
                os.utime (file, None)
        else:
                file = open (file,"w")
                file.close ()

def get_primary_mirror (project):

        if project.has("mirror/primary_host"):
                m = project.node("mirror")

                mirror = m.text("primary_proto") + "://"
                mirror +=m.text("primary_host")  + "/"
                mirror +=m.text("primary_path")

        elif project.has("mirror/cdrom"):
                 mirror = "file://%s/debian" % cdrompath

        return mirror.replace("LOCALMACHINE", "10.0.2.2")

def create_apt_sources_list (project, rfs_path, log):

        if not project.has("mirror") and not project.has("mirror/cdrom"):
                return "# no mirrors configured"

        if project.has("mirror/primary_host"):
                mirror  = "deb " + get_primary_mirror (project)
                mirror += " " + project.text("suite") + " main\n"

                for url in project.node("mirror/url-list"):
                      if url.has("binary"):
                           mirror += "deb " + url.text("binary").strip() + "\n"
                      if url.has("source"):
                           mirror += "deb-src "+url.text("source").strip()+"\n"

        if project.has("mirror/cdrom"):
                cdrompath = os.path.join( rfs_path, "cdrom" )
                log.do( 'mkdir -p "%s"' % cdrompath )
                log.do( 'mount -o loop "%s" "%s"'
                   % (prj.text("mirror/cdrom"), cdrompath ) )

                mirror += "deb copy:///mnt %s main\n" % (project.text("suite"))

        return mirror.replace("LOCALMACHINE", "10.0.2.2")


class RFS:
        def __init__ (self, project, target, defs, log,
                      path="virtual", install_recommends="0"):

                self.project = project
                self.target = target
                self.defs = defs
                self.log = log
                self.rfs_dir = path

                self.suite = project.text ("suite")

                self.arch = project.text(
                   "buildimage/arch", default=defs, key="arch")

                self.host_arch = log.get_command_out(
                  "dpkg --print-architecture").strip ()

                self.primary_mirror = get_primary_mirror (project)

                self.virtual = False
                if path == "virtual":
                        self.virtual = True
                        self.rfs_dir = mkdtemp()
                # TODO think about reinitialization if elbe_version differs
                elif not os.path.isfile(self.rfs_dir + "/etc/elbe_version"):
                        self.debootstrap ()
                else:
                        print 'work on existing rfs'

                self.initialize_dirs ()
                # TODO: self.create_apt_prefs (prefs)

                apt_pkg.config.set ("APT::Install-Recommends",
                    install_recommends)

                apt_pkg.config.set ("APT::Architecture", self.arch)
                apt_pkg.config.set ("Dir", self.rfs_dir)
                apt_pkg.config.set ("APT::Cache-Limit", "0")
                apt_pkg.config.set ("APT::Cache-Start", "32505856")
                apt_pkg.config.set ("APT::Cache-Grow", "2097152")
                apt_pkg.config.set ("Dir::State", "state")
                apt_pkg.config.set ("Dir::State::status", "status")
                apt_pkg.config.set ("Dir::Cache", "cache")
                apt_pkg.config.set ("Dir::Etc", "etc/apt")
                apt_pkg.config.set ("Dir::Log", "log")
                noauth = "0"
                if project.has("noauth"):
                        noauth = "1"
                apt_pkg.config.set ("APT::Get::AllowUnauthenticated", noauth)

                apt_pkg.init_system()

                self.source = apt_pkg.SourceList ()
                self.source.read_main_list()
                self.cache = apt_pkg.Cache ()
                try:
                        self.cache.update(self,self.source)
                except:
                        pass

                # TODO don't knwo why we need the following code,
                #        but also no idea why wheezy is invalid ..
                #
                # Traceback (most recent call last):
                #   File "<input>", line 1, in <module>
                #   File "elbepack/rfs.py", line 127, in __init__
                #     self.cache = apt_pkg.Cache ()
                # SystemError: E:The value 'wheezy' is invalid for
                #    APT::Default-Release as such a
                # release is not available in the sources

                #apt_pkg.config.set ("APT::Default-Release", self.suite)
                #self.cache = apt_pkg.Cache ()
                #try:
                #    self.cache.update(self,self.source)
                #except:
                #    pass

        def __del__(self):

                if self.virtual:
                        os.system( 'rm -rf "%s"' % self.rfs_dir )

                elif self.host_arch != self.arch:
                        self.log.do( 'rm -f %s' %
                           os.path.join(self.rfs_dir,
                                        "usr/bin"+self.defs["userinterpr"] ))

                if self.project.has ("mirror/cdrom"):
                        cdrompath = os.path.join( self.rfs_path, "cdrom" )
                        self.log.do ('umount "%s"' % cdrompath)

        def write_version (self):

                f = file(os.path.join(self.rfs_dir, "etc/elbe_version"), "w+")

                f.write("%s %s\n" % (self.project.text("name"),
                                   self.project.text("version")))

                f.write("this RFS was generated by elbe %s\n" % (elbe_version))
                f.write(time.strftime("%c"))

                f.close()

        def debootstrap (self):

                if self.project.has("mirror/primary_proxy"):
                        os.environ["http_proxy"] = self.project.text(
                                                     "mirror/primary_proxy")

                os.environ["LANG"] = "C"
                os.environ["LANGUAGE"] = "C"
                os.environ["LC_ALL"] = "C"
                os.environ["DEBIAN_FRONTEND"]="noninteractive"
                os.environ["DEBONF_NONINTERACTIVE_SEEN"]="true"

                self.log.h2( "debootstrap log" )

                if self.host_arch == self.arch:
                    cmd = 'debootstrap "%s" "%s" "%s"' % (
                                self.suite, self.rfs_dir, self.primary_mirror)

                    self.log.do( cmd )

                    return

                cmd = 'debootstrap --foreign --arch=%s "%s" "%s" "%s"' % (
                    self.arch, self.suite, self.rfs_dir, self.primary_mirror)

                self.log.do (cmd)

                self.log.do ('cp /usr/bin/%s %s' % (self.defs["userinterpr"],
                    os.path.join(self.rfs_dir, "usr/bin" )) )

                self.log.chroot (self.rfs_dir,
                                 '/debootstrap/debootstrap --second-stage')

                self.log.chroot (self.rfs_dir, 'dpkg --configure -a')

                self.write_version ()


        def start (self):
                pass

        def stop (self):
                pass

        def pulse (self, obj):
                #print "updating in progress", obj
                return True

        def initialize_dirs (self):
                mkdir_p (self.rfs_dir + "/cache/archives/partial")
                mkdir_p (self.rfs_dir + "/etc/apt/preferences.d")
                mkdir_p (self.rfs_dir + "/db")
                mkdir_p (self.rfs_dir + "/log")
                mkdir_p (self.rfs_dir + "/state/lists/partial")
                touch_file (self.rfs_dir + "/state/status")

                mirror = create_apt_sources_list (
                                self.project, self.rfs_dir, self.log)

                sources_list = self.rfs_dir + "/etc/apt/sources.list"

                if os.path.exists (sources_list):
                        os.remove (sources_list)

                sl_file = open (sources_list, "w")
                sl_file.write (mirror)
                sl_file.close ()

        def create_apt_prefs (self, prefs):
                filename = self.rfs_dir + "/etc/apt/preferences"

                if os.path.exists (filename):
                        os.remove (filename)

                file = open (filename,"w")
                file.write (prefs)
                file.close ()