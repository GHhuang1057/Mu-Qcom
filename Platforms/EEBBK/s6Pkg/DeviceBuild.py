##
# Copyright (c) Microsoft Corporation.
# SPDX-License-Identifier: BSD-2-Clause-Patent
##

import datetime
import logging
import os
import sys  # 确保已导入sys

from io import StringIO
from pathlib import Path

from edk2toolext.environment import shell_environment
from edk2toolext.environment.uefi_build import UefiBuilder
from edk2toolext.invocables.edk2_platform_build import BuildSettingsManager
from edk2toolext.invocables.edk2_pr_eval import PrEvalSettingsManager
from edk2toolext.invocables.edk2_setup import (RequiredSubmodule, SetupSettingsManager)
from edk2toolext.invocables.edk2_update import UpdateSettingsManager
from edk2toolext.invocables.edk2_parse import ParseSettingsManager
from edk2toollib.utility_functions import RunCmd

# ####################################################################################### #
#                                Common Configuration                                     #
# ####################################################################################### #
class CommonPlatform ():
    PackagesSupported = ("s6Pkg")
    ArchSupported = ("AARCH64")
    TargetsSupported = ("DEBUG", "RELEASE")
    Scopes = ('s6', 'gcc_aarch64_linux', 'edk2-build')
    
    # 修复工作空间路径计算
    WorkspaceRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 添加 DSC 文件路径变量
    DscPath = "s6Pkg/s6.dsc"
    
    PackagesPath = (
        "Platforms/Lenovo",
        "Common/Mu",
        "Common/Mu_OEM_Sample",
        "Common/Mu_Tiano_Plus",
        "Features/DFCI",
        "Mu_Basecore",
        "Silicon/Arm/Mu_Tiano",
        "Silicon/Qualcomm",
        "Silicon/Silicium",
        "Silicium-ACPI/SoCs/Qualcomm"
    )

# ####################################################################################### #
#                         Configuration for Update & Setup                                #
# ####################################################################################### #
class SettingsManager (UpdateSettingsManager, SetupSettingsManager, PrEvalSettingsManager, ParseSettingsManager):

    def GetPackagesSupported (self):
        return CommonPlatform.PackagesSupported

    def GetArchitecturesSupported (self):
        return CommonPlatform.ArchSupported

    def GetTargetsSupported (self):
        return CommonPlatform.TargetsSupported

    def GetRequiredSubmodules (self):
        required = [
            # 修复参数传递方式 - 使用关键字参数
            RequiredSubmodule("Binaries", optional=True, recursive=False),
            RequiredSubmodule("Common/Mu", optional=True),
            RequiredSubmodule("Common/Mu_OEM_Sample", optional=True),
            RequiredSubmodule("Common/Mu_Tiano_Plus", optional=True),
            RequiredSubmodule("Features/DFCI", optional=True),
            RequiredSubmodule("Mu_Basecore", optional=True),
            RequiredSubmodule("Silicon/Arm/Mu_Tiano", optional=True),
            RequiredSubmodule("Silicium-ACPI", optional=True),
        ]
        
        # 添加子模块路径验证
        workspace = self.GetWorkspaceRoot()
        for submodule in required:
            sub_path = os.path.join(workspace, submodule.path)
            if not os.path.exists(sub_path):
                logging.error(f"Submodule path missing: {sub_path}")
            elif not os.path.exists(os.path.join(sub_path, ".git")):
                logging.error(f"Submodule not initialized: {sub_path}")
                
        return required

    def SetArchitectures (self, list_of_requested_architectures):
        unsupported = set(list_of_requested_architectures) - set(self.GetArchitecturesSupported())

        if (len(unsupported) > 0):
            errorString = ("Unsupported Architecture Requested: " + " ".join(unsupported))
            logging.critical (errorString)
            raise Exception (errorString)

        self.ActualArchitectures = list_of_requested_architectures

    def GetWorkspaceRoot (self):
        return CommonPlatform.WorkspaceRoot

    def GetActiveScopes (self):
        return CommonPlatform.Scopes

    def FilterPackagesToTest (self, changedFilesList: list, potentialPackagesList: list) -> list:
        build_these_packages = []
        possible_packages = potentialPackagesList.copy ()

        for f in changedFilesList:
            if "BaseTools" in f:
                if os.path.splitext(f) not in [".txt", ".md"]:
                    build_these_packages = possible_packages
                    break

            if "platform-build-run-steps.yml" in f:
                build_these_packages = possible_packages
                break

        return build_these_packages

    def GetPlatformDscAndConfig (self) -> tuple:
        # 使用绝对路径确保可靠解析
        dsc_path = os.path.join(CommonPlatform.WorkspaceRoot, CommonPlatform.DscPath)
        if not os.path.isfile(dsc_path):
            logging.error(f"DSC file not found at: {dsc_path}")
            logging.error(f"Current directory: {os.getcwd()}")
            if os.path.exists(os.path.dirname(dsc_path)):
                logging.error(f"Directory contents: {os.listdir(os.path.dirname(dsc_path))}")
            raise FileNotFoundError(f"DSC file missing: {dsc_path}")
        return (CommonPlatform.DscPath, {})

    def GetName (self):
        return "s6"

    def GetPackagesPath (self):
        return CommonPlatform.PackagesPath

# ####################################################################################### #
#                         Actual Configuration for Platform Build                         #
# ####################################################################################### #
class PlatformBuilder (UefiBuilder, BuildSettingsManager):
    def __init__ (self):
        UefiBuilder.__init__ (self)

    def AddCommandLineOptions (self, parserObj):
        parserObj.add_argument('-a', "--arch", dest="build_arch", type=str, default="AARCH64", help="Optional - CSV of architecture to build. AARCH64 is used for PEI and DXE and is the only valid option for this platform.")

    def RetrieveCommandLineOptions (self, args):
        if args.build_arch.upper() != "AARCH64":
            raise Exception("Invalid Arch Specified.  Please see comments in DeviceBuild.py::PlatformBuilder::AddCommandLineOptions")

    def GetWorkspaceRoot (self):
        return CommonPlatform.WorkspaceRoot

    def GetPackagesPath (self):
        result = [ shell_environment.GetBuildVars().GetValue("FEATURE_CONFIG_PATH", "") ]

        for a in CommonPlatform.PackagesPath:
            result.append(a)

        return result

    def GetActiveScopes (self):
        return CommonPlatform.Scopes

    def GetName (self):
        return "s6Pkg"

    def GetLoggingLevel (self, loggerType):
        return logging.INFO

    def SetPlatformEnv (self):
        logging.debug ("PlatformBuilder SetPlatformEnv")

        # 添加路径验证
        workspace = self.GetWorkspaceRoot()
        dsc_path = os.path.join(workspace, CommonPlatform.DscPath)
        if not os.path.isfile(dsc_path):
            logging.critical(f"DSC file not found: {dsc_path}")
            logging.critical(f"Current directory: {os.getcwd()}")
            if os.path.exists(workspace):
                logging.critical(f"Workspace contents: {os.listdir(workspace)}")
            if os.path.exists(os.path.join(workspace, "s6Pkg")):
                logging.critical(f"s6Pkg contents: {os.listdir(os.path.join(workspace, 's6Pkg'))}")
            raise FileNotFoundError("Critical DSC file missing")
        
        self.env.SetValue ("PRODUCT_NAME", "s6", "Platform Hardcoded")
        self.env.SetValue ("ACTIVE_PLATFORM", CommonPlatform.DscPath, "Platform Hardcoded")
        self.env.SetValue ("TARGET_ARCH", "AARCH64", "Platform Hardcoded")
        self.env.SetValue ("TOOL_CHAIN_TAG", "CLANGPDB", "set default to clangpdb")
        self.env.SetValue ("EMPTY_DRIVE", "FALSE", "Default to false")
        self.env.SetValue ("RUN_TESTS", "FALSE", "Default to false")
        self.env.SetValue ("SHUTDOWN_AFTER_RUN", "FALSE", "Default to false")
        self.env.SetValue ("BLD_*_BUILDID_STRING", "Unknown", "Default")
        self.env.SetValue ("BUILDREPORTING", "TRUE", "Enabling build report")
        self.env.SetValue ("BUILDREPORT_TYPES", "PCD DEPEX FLASH BUILD_FLAGS LIBRARY FIXED_ADDRESS HASH", "Setting build report types")
        self.env.SetValue ("BLD_*_MEMORY_PROTECTION", "TRUE", "Default")
        self.env.SetValue ("BLD_*_SHIP_MODE", "FALSE", "Default")
        self.env.SetValue ("BLD_*_FD_BASE", self.env.GetValue("FD_BASE"), "Default")
        self.env.SetValue ("BLD_*_FD_SIZE", self.env.GetValue("FD_SIZE"), "Default")
        self.env.SetValue ("BLD_*_FD_BLOCKS", self.env.GetValue("FD_BLOCKS"), "Default")

        return 0

    def PlatformPreBuild (self):
        return 0

    def PlatformPostBuild (self):
        return 0

    def FlashRomImage (self):
        return 0

if __name__ == "__main__":
    import argparse

    from edk2toolext.invocables.edk2_platform_build import Edk2PlatformBuild
    from edk2toolext.invocables.edk2_setup import Edk2PlatformSetup
    from edk2toolext.invocables.edk2_update import Edk2Update

    # 配置详细日志
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    SCRIPT_PATH = os.path.relpath (__file__)

    parser = argparse.ArgumentParser (add_help=False)

    parse_group = parser.add_mutually_exclusive_group()

    parse_group.add_argument ("--update", "--UPDATE", action='store_true', help="Invokes stuart_update")
    parse_group.add_argument ("--setup",  "--SETUP",  action='store_true', help="Invokes stuart_setup")

    args, remaining = parser.parse_known_args()

    new_args = ["stuart", "-c", SCRIPT_PATH]
    new_args = new_args + remaining

    sys.argv = new_args

    if args.setup:
        try:
            Edk2PlatformSetup().Invoke()
        except Exception as e:
            logging.exception("Setup failed with exception")
            sys.exit(1)
    elif args.update:
        try:
            Edk2Update().Invoke()
        except Exception as e:
            logging.exception("Update failed with exception")
            sys.exit(1)
    else:
        try:
            Edk2PlatformBuild().Invoke()
        except Exception as e:
            logging.exception("Build failed with exception")
            sys.exit(1)