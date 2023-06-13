import yaml
from pathlib import Path

def read_config_file(path):
    # read config files from path and return its contents
    with open(path) as f:
        config_dict = yaml.load(f, Loader=yaml.FullLoader)

    return config_dict


def write_config_file(content, path):
    with open(path.joinpath(content["general"]["project_name"] + "_config.yaml"), "w") as f:
        yaml.dump(content, f, default_flow_style=False, sort_keys=False)


if __name__ == '__main__':
    config = read_config_file(Path.cwd().parent.joinpath("example_config.yaml"))
    print(config)

    write_config_file(content=config, path=Path.cwd().parent)