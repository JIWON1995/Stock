from .sectors import get_top_level_sectors


def sector_menu(request):
    return {
        'sector_menu': get_top_level_sectors(),
        'current_sector': request.GET.get('sector', ''),
    }
