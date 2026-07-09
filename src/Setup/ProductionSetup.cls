Class Setup.ProductionSetup
{

ClassMethod Setup(fileWatcherRoot As %String, envSetup As %Boolean = 0) As %Status [ Language = python ]
{
    import sys
    import iris
    import intersystems_pyprod
    import subprocess as sb
    import os
    from pathlib import Path

    lib_dir = iris.system.Util.InstallDirectory() + "lib/"
    #; print(lib_dir)
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)

    pyprod_bin_path = Path(intersystems_pyprod.__file__).resolve().parent.parent / "bin"

    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    #; print(pyprod_bin_path)
    if str(pyprod_bin_path) not in path_entries:
        path_entries.append(str(pyprod_bin_path))
        os.environ["PATH"] = os.pathsep.join(path_entries)

    if envSetup:
        iris.cls("Setup.ProductionSetup").SetupEnv()

    iris.cls("Setup.ProductionSetup").DirectorySetup(fileWatcherRoot)

    result = sb.run(
        f"intersystems_pyprod {lib_dir}smart-grid-pyprod/smart_grid.py",
        capture_output=True,
        text=True,
        check=True,
        shell=True,

    )

    print(result.stdout, result.stderr)
    
    return 1
}

ClassMethod SetupEnv() As %Status [ Language = python ]
{
    import os
    import iris

    install_dir = iris.system.Util.InstallDirectory()
    namespace = iris._SYSTEM.SYS.NameSpace()
    os.environ["IRISINSTALLDIR"] = install_dir
    os.environ["IRISNAMESPACE"] = namespace
    os.environ["IRISUSERNAME"] = "SuperUser"
    os.environ["IRISPASSWORD"] = "SYS"

    lib_python = install_dir + "lib/python"
    bin_python = lib_python + "/bin"

    existing_pythonpath = os.environ.get("PYTHONPATH", "")
    if lib_python not in existing_pythonpath:
        os.environ["PYTHONPATH"] = lib_python + (":" + existing_pythonpath if existing_pythonpath else "")

    existing_path = os.environ.get("PATH", "")
    if bin_python not in existing_path:
        os.environ["PATH"] = bin_python + (":" + existing_path if existing_path else "")

    existing_ld = os.environ.get("LD_LIBRARY_PATH", "")
    iris_bin = install_dir + "bin"
    if iris_bin not in existing_ld:
        os.environ["LD_LIBRARY_PATH"] = iris_bin + (":" + existing_ld if existing_ld else "")

    return 1
}

/// Set directories for in and out files
ClassMethod DirectorySetup(fileWatcherRoot As %String) As %Status [ Language = python ]
{
    import os
    import re
    import iris

    root = str(fileWatcherRoot)

    if not os.path.exists(root):
        os.makedirs(root)

    for subdir in ["input", "archive", "processing"]:
        subdir_path = os.path.join(root, subdir)
        if not os.path.exists(subdir_path):
            os.makedirs(subdir_path)

    production_py =  iris.system.Util.InstallDirectory() +"lib/smart-grid-pyprod/smart_grid.py"
    with open(production_py, "r") as f:
        content = f.read()

    content = re.sub(
        r'^FILE_WATCHER_ROOT\s*=\s*.+$',
        f'FILE_WATCHER_ROOT = "{root}"',
        content,
        flags=re.MULTILINE
    )

    with open(production_py, "w") as f:
        f.write(content)

    return 1
}

ClassMethod StartProduction() As %Status [ Language = python ]
{
    from intersystems_pyprod import director
    print("Starting Production...")
    status = director.start_production("EnergyOps.Prod")
    if status!= 1:
        status = director.restart_production()

    return status
}

}
